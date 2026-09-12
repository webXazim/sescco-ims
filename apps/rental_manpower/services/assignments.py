from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit
from apps.accounts.roles import Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.contracts import ProjectStatus
from apps.projects.models import Project
from apps.rental_manpower.project_adapter import project_public_id, rental_project_for_company, validate_rental_project_date
from apps.rental_manpower.models import (
    AssignmentChangeType,
    ManpowerSupplier,
    ReleaseDisposition,
    RentalRateType,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    WorkerAssignment,
    RentalTimesheetEntry,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
)


def _require_rental_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.RENTAL):
        raise PermissionDenied("Your role cannot modify rental manpower assignments.")


def _decimal_rate(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"rate": "Enter a valid assignment rate."}) from exc
    if not result.is_finite() or result <= 0:
        raise ValidationError({"rate": "Assignment rate must be greater than zero."})
    return result


def _rate_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError({"rate_type": "Rate type must be Hourly, Daily, or Monthly."})
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "hourly": RentalRateType.HOURLY,
        "daily": RentalRateType.DAILY,
        "monthly": RentalRateType.MONTHLY,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError({"rate_type": "Rate type must be Hourly, Daily, or Monthly."}) from exc


def _release_disposition(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError({"disposition": "Release disposition must be Available or Inactive."})
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "available": ReleaseDisposition.AVAILABLE,
        "inactive": ReleaseDisposition.INACTIVE,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError({"disposition": "Release disposition must be Available or Inactive."}) from exc


def _snapshot(assignment: WorkerAssignment) -> dict[str, object]:
    return {
        "worker_id": str(assignment.worker_id),
        "worker_number": assignment.worker.worker_number,
        "supplier_id": str(assignment.worker.supplier_id),
        "project_id": project_public_id(assignment.project),
        "project_code": assignment.project.code,
        "trade": assignment.trade,
        "rate_type": assignment.rate_type,
        "rate": str(assignment.rate),
        "effective_from": assignment.effective_from.isoformat(),
        "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "change_type": assignment.change_type,
        "reason": assignment.reason,
        "end_reason": assignment.end_reason,
        "end_notes": assignment.end_notes,
        "release_disposition": assignment.release_disposition,
        "cancelled_at": assignment.cancelled_at.isoformat() if assignment.cancelled_at else None,
        "cancel_reason": assignment.cancel_reason,
    }


def _lock_worker(*, company, worker_id) -> RentalWorker:
    worker = (
        RentalWorker.objects.select_for_update()
        .select_related("supplier")
        .get(pk=worker_id, company=company)
    )
    if worker.deleted_at:
        raise ValidationError({"worker": "Restore the deleted rental worker before changing assignments."})
    if worker.archived_at:
        raise ValidationError({"worker": "Restore the archived rental worker before changing assignments."})
    if worker.supplier.deleted_at:
        raise ValidationError({"worker": "Restore the worker's deleted manpower supplier before changing assignments."})
    if worker.supplier.archived_at:
        raise ValidationError({"worker": "Restore the worker's archived manpower supplier before changing assignments."})
    if worker.status != RentalWorkerStatus.ACTIVE:
        raise ValidationError({"worker": "Only an active rental-worker master can be assigned."})
    if worker.supplier.status != SupplierStatus.ACTIVE:
        raise ValidationError({"worker": "The worker's manpower supplier is inactive."})
    return worker


def _lock_project(*, company, project_id, require_active: bool) -> Project:
    project = rental_project_for_company(
        company=company, identifier=project_id, for_update=True, require_active=require_active
    )
    if not require_active and project.status in {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}:
        raise ValidationError({"project": "A completed or archived project cannot receive assignment changes."})
    return project


def _validate_project_date(*, project: Project, effective_date: date) -> None:
    try:
        validate_rental_project_date(project=project, work_date=effective_date, require_active=False)
    except ValidationError as exc:
        messages = getattr(exc, "message_dict", {}).get("project")
        message = messages[0] if messages else "The assignment date is outside the project lifecycle."
        raise ValidationError({"effective_date": message}) from exc


def _assert_timesheet_snapshot_safe(*, company, worker_id, project_id, affected_from: date) -> None:
    """Prevent assignment changes from invalidating already-saved rental timesheet snapshots."""
    if RentalTimesheetEntry.objects.for_company(company).filter(
        worker_id=worker_id, period__project_id=project_id, work_date__gte=affected_from
    ).exists():
        raise ValidationError({
            "effective_date": "Saved rental-timesheet rows already exist on or after this date. Clear the affected Draft rows before changing assignment history."
        })
    if RentalTimesheetPeriod.objects.for_company(company).filter(
        project_id=project_id, period_end__gte=affected_from,
        status__in=[RentalTimesheetStatus.SUBMITTED, RentalTimesheetStatus.APPROVED, RentalTimesheetStatus.LOCKED],
    ).exists():
        raise ValidationError({
            "effective_date": "A reviewed or locked project timesheet already covers this effective date. Assignment history cannot be changed retroactively."
        })


def _assignment_overlap_exists(*, company, worker_id, start: date, end: date | None = None, exclude_id=None) -> bool:
    queryset = WorkerAssignment.objects.for_company(company).filter(worker_id=worker_id, cancelled_at__isnull=True)
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    queryset = queryset.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
    if end is not None:
        queryset = queryset.filter(effective_from__lte=end)
    return queryset.exists()


def _latest_open_assignment(*, company, worker: RentalWorker) -> WorkerAssignment:
    assignment = (
        WorkerAssignment.objects.select_for_update()
        .select_related("worker", "worker__supplier", "project")
        .filter(company=company, worker=worker, effective_to__isnull=True, cancelled_at__isnull=True)
        .order_by("-effective_from", "-created_at")
        .first()
    )
    if not assignment:
        raise ValidationError({"assignment": "The worker has no open assignment for this lifecycle action."})
    if assignment.effective_from > timezone.localdate():
        raise ValidationError({
            "assignment": "A future scheduled assignment change already exists. Cancel it before recording another lifecycle change."
        })
    return assignment


def _create_segment(
    *,
    company,
    worker: RentalWorker,
    project: Project,
    trade: str,
    rate_type: str,
    rate,
    effective_from: date,
    change_type: str,
    reason: str,
) -> WorkerAssignment:
    if not isinstance(effective_from, date):
        raise ValidationError({"effective_date": "A valid effective date is required."})
    trade = (trade or "").strip()
    if not trade:
        raise ValidationError({"trade": "Trade / role is required."})
    if _assignment_overlap_exists(company=company, worker_id=worker.pk, start=effective_from):
        raise ValidationError({"effective_date": "This assignment would overlap existing worker assignment history."})
    assignment = WorkerAssignment(
        company=company,
        worker=worker,
        project=project,
        trade=trade,
        rate_type=_rate_type(rate_type),
        rate=_decimal_rate(rate),
        effective_from=effective_from,
        change_type=change_type,
        reason=(reason or "").strip(),
    )
    assignment.full_clean()
    try:
        assignment.save()
    except IntegrityError as exc:
        raise ValidationError("The assignment conflicts with an existing worker assignment.") from exc
    return assignment


def _record_transition(
    *,
    assignment: WorkerAssignment,
    action: str,
    actor_membership: CompanyMembership,
    before: dict[str, object] | None,
    request: HttpRequest | None,
    metadata: dict[str, object] | None = None,
) -> None:
    record_audit_event(
        company=assignment.company,
        area=AuditArea.RENTAL,
        action=action,
        object_type="rental_manpower.WorkerAssignment",
        object_id=assignment.pk,
        object_label=f"{assignment.worker.worker_number} · {assignment.project.code}",
        actor_membership=actor_membership,
        before=before,
        after=_snapshot(assignment),
        metadata=metadata or {},
        request=request,
    )


@transaction.atomic
def assign_worker(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    project_id,
    trade: str,
    rate_type: str,
    rate,
    effective_date: date,
    reason: str = "",
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    project = _lock_project(company=company, project_id=project_id, require_active=True)
    _validate_project_date(project=project, effective_date=effective_date)
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=project.pk, affected_from=effective_date)
    assignment = _create_segment(
        company=company,
        worker=worker,
        project=project,
        trade=trade,
        rate_type=rate_type,
        rate=rate,
        effective_from=effective_date,
        change_type=AssignmentChangeType.ASSIGNMENT,
        reason=reason or "Project assignment",
    )
    _record_transition(
        assignment=assignment,
        action="rental.assignment.assigned",
        actor_membership=actor_membership,
        before=None,
        request=request,
    )
    return assignment


def _close_for_revision(*, assignment: WorkerAssignment, new_effective_date: date, reason: str) -> dict[str, object]:
    if new_effective_date <= assignment.effective_from:
        raise ValidationError({
            "effective_date": "The new effective date must be after the current assignment start date."
        })
    before = _snapshot(assignment)
    assignment.effective_to = new_effective_date - timedelta(days=1)
    assignment.end_reason = (reason or "").strip()
    assignment.release_disposition = ""
    assignment.full_clean()
    assignment.save(update_fields=("effective_to", "end_reason", "release_disposition", "updated_at"))
    return before


@transaction.atomic
def transfer_worker(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    project_id,
    trade: str,
    rate_type: str,
    rate,
    effective_date: date,
    reason: str = "",
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    current = _latest_open_assignment(company=company, worker=worker)
    project = _lock_project(company=company, project_id=project_id, require_active=True)
    if current.project_id == project.pk:
        raise ValidationError({"project": "A project transfer must move the worker to a different project."})
    _validate_project_date(project=project, effective_date=effective_date)
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=current.project_id, affected_from=effective_date)
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=project.pk, affected_from=effective_date)
    previous_snapshot = _close_for_revision(
        assignment=current,
        new_effective_date=effective_date,
        reason=reason or "Project transfer",
    )
    assignment = _create_segment(
        company=company,
        worker=worker,
        project=project,
        trade=trade,
        rate_type=rate_type,
        rate=rate,
        effective_from=effective_date,
        change_type=AssignmentChangeType.TRANSFER,
        reason=reason or "Project transfer",
    )
    _record_transition(
        assignment=assignment,
        action="rental.assignment.transferred",
        actor_membership=actor_membership,
        before=previous_snapshot,
        request=request,
        metadata={"previous_assignment_id": str(current.pk)},
    )
    return assignment


@transaction.atomic
def change_worker_trade(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    trade: str,
    effective_date: date,
    rate_type: str | None = None,
    rate=None,
    reason: str = "",
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    current = _latest_open_assignment(company=company, worker=worker)
    project = _lock_project(company=company, project_id=current.project_id, require_active=False)
    next_trade = (trade or "").strip()
    if not next_trade:
        raise ValidationError({"trade": "Trade / role is required."})
    if next_trade.casefold() == current.trade.casefold():
        raise ValidationError({"trade": "Choose a different trade / role."})
    next_rate_type = rate_type or current.rate_type
    next_rate = current.rate if rate in (None, "") else rate
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=current.project_id, affected_from=effective_date)
    previous_snapshot = _close_for_revision(
        assignment=current,
        new_effective_date=effective_date,
        reason=reason or "Trade / role change",
    )
    assignment = _create_segment(
        company=company,
        worker=worker,
        project=project,
        trade=next_trade,
        rate_type=next_rate_type,
        rate=next_rate,
        effective_from=effective_date,
        change_type=AssignmentChangeType.TRADE_CHANGE,
        reason=reason or "Trade / role change",
    )
    _record_transition(
        assignment=assignment,
        action="rental.assignment.trade_changed",
        actor_membership=actor_membership,
        before=previous_snapshot,
        request=request,
        metadata={"previous_assignment_id": str(current.pk)},
    )
    return assignment


@transaction.atomic
def change_worker_rate(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    rate_type: str,
    rate,
    effective_date: date,
    reason: str = "",
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    current = _latest_open_assignment(company=company, worker=worker)
    project = _lock_project(company=company, project_id=current.project_id, require_active=False)
    normalized_type = _rate_type(rate_type)
    normalized_rate = _decimal_rate(rate)
    if normalized_type == current.rate_type and normalized_rate == current.rate:
        raise ValidationError({"rate": "Choose a different rate or rate type."})
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=current.project_id, affected_from=effective_date)
    previous_snapshot = _close_for_revision(
        assignment=current,
        new_effective_date=effective_date,
        reason=reason or "Rate revision",
    )
    assignment = _create_segment(
        company=company,
        worker=worker,
        project=project,
        trade=current.trade,
        rate_type=normalized_type,
        rate=normalized_rate,
        effective_from=effective_date,
        change_type=AssignmentChangeType.RATE_CHANGE,
        reason=reason or "Rate revision",
    )
    _record_transition(
        assignment=assignment,
        action="rental.assignment.rate_changed",
        actor_membership=actor_membership,
        before=previous_snapshot,
        request=request,
        metadata={"previous_assignment_id": str(current.pk)},
    )
    return assignment


@transaction.atomic
def release_worker(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    effective_date: date,
    disposition: str,
    reason: str = "",
    note: str = "",
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    assignment = _latest_open_assignment(company=company, worker=worker)
    if effective_date < assignment.effective_from:
        raise ValidationError({"effective_date": "Release date cannot be before the assignment start date."})
    if effective_date > timezone.localdate():
        raise ValidationError({"effective_date": "Release must use an actual last-working date of today or earlier."})
    release_to = _release_disposition(disposition)
    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=assignment.project_id, affected_from=effective_date + timedelta(days=1))
    before = _snapshot(assignment)
    assignment.effective_to = effective_date
    assignment.end_reason = (reason or "Released from project").strip()
    assignment.end_notes = (note or "").strip()
    assignment.release_disposition = release_to
    assignment.full_clean()
    assignment.save(update_fields=("effective_to", "end_reason", "end_notes", "release_disposition", "updated_at"))
    if release_to == ReleaseDisposition.INACTIVE:
        prior_worker_status = worker.status
        worker.status = RentalWorkerStatus.INACTIVE
        worker.inactive_on = effective_date
        worker.inactive_reason = (reason or "Released from project").strip()
        worker.full_clean()
        worker.save(update_fields=("status", "inactive_on", "inactive_reason", "updated_at"))
        record_audit_event(
            company=company,
            area=AuditArea.RENTAL,
            action="rental.worker.inactivated_after_release",
            object_type="rental_manpower.RentalWorker",
            object_id=worker.pk,
            object_label=str(worker),
            actor_membership=actor_membership,
            before={"status": prior_worker_status},
            after={"status": worker.status, "assignment_id": str(assignment.pk)},
            request=request,
        )
    record_audit_event(
        company=company,
        area=AuditArea.RENTAL,
        action="rental.assignment.released",
        object_type="rental_manpower.WorkerAssignment",
        object_id=assignment.pk,
        object_label=f"{worker.worker_number} · {assignment.project.code}",
        actor_membership=actor_membership,
        before=before,
        after=_snapshot(assignment),
        metadata={"disposition": release_to},
        request=request,
    )
    return assignment


@transaction.atomic
def cancel_scheduled_assignment(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    reason: str,
    request: HttpRequest | None = None,
) -> WorkerAssignment:
    """Cancel the worker's latest future open segment without inventing worked history.

    If the future segment was created by transfer/trade/rate revision, the predecessor
    segment is reopened. Initial future assignments simply become retained cancelled
    records.
    """
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    worker = _lock_worker(company=company, worker_id=worker_id)
    assignment = (
        WorkerAssignment.objects.select_for_update()
        .select_related("worker", "worker__supplier", "project")
        .filter(
            company=company,
            worker=worker,
            effective_to__isnull=True,
            cancelled_at__isnull=True,
            effective_from__gt=timezone.localdate(),
        )
        .order_by("-effective_from", "-created_at")
        .first()
    )
    if not assignment:
        raise ValidationError({"assignment": "The worker has no future scheduled assignment to cancel."})
    cancel_reason = (reason or "").strip()
    if not cancel_reason:
        raise ValidationError({"reason": "A cancellation reason is required."})

    _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=assignment.project_id, affected_from=assignment.effective_from)
    before = _snapshot(assignment)
    predecessor = None
    if assignment.change_type != AssignmentChangeType.ASSIGNMENT:
        predecessor = (
            WorkerAssignment.objects.select_for_update()
            .select_related("worker", "worker__supplier", "project")
            .filter(
                company=company,
                worker=worker,
                cancelled_at__isnull=True,
                effective_to=assignment.effective_from - timedelta(days=1),
            )
            .order_by("-effective_from", "-created_at")
            .first()
        )
        if predecessor is None or predecessor.release_disposition:
            raise ValidationError({"assignment": "The scheduled revision cannot be cancelled because its predecessor cannot be safely restored."})
        if predecessor.project_id != assignment.project_id:
            _assert_timesheet_snapshot_safe(company=company, worker_id=worker.pk, project_id=predecessor.project_id, affected_from=assignment.effective_from)

    assignment.cancelled_at = timezone.now()
    assignment.cancel_reason = cancel_reason
    assignment.full_clean()
    assignment.save(update_fields=("cancelled_at", "cancel_reason", "updated_at"))

    if predecessor is not None:
        predecessor_before = _snapshot(predecessor)
        predecessor.effective_to = None
        predecessor.end_reason = ""
        predecessor.full_clean()
        predecessor.save(update_fields=("effective_to", "end_reason", "updated_at"))
        record_audit_event(
            company=company,
            area=AuditArea.RENTAL,
            action="rental.assignment.predecessor_reopened",
            object_type="rental_manpower.WorkerAssignment",
            object_id=predecessor.pk,
            object_label=f"{worker.worker_number} · {predecessor.project.code}",
            actor_membership=actor_membership,
            before=predecessor_before,
            after=_snapshot(predecessor),
            metadata={"cancelled_assignment_id": str(assignment.pk)},
            request=request,
        )

    _record_transition(
        assignment=assignment,
        action="rental.assignment.cancelled",
        actor_membership=actor_membership,
        before=before,
        request=request,
        metadata={"reopened_assignment_id": str(predecessor.pk) if predecessor else None},
    )
    return assignment
