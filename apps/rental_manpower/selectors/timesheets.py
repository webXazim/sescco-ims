from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, Count, DecimalField, Exists, F, OuterRef, Q, Sum, Value, When

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.core.payroll_attendance_contract import ATTENDANCE_WORKSPACE_RENTAL, attendance_contract_payload
from apps.rental_manpower.models import (
    RentalAdjustment,
    RentalAdjustmentStatus,
    RentalAdjustmentType,
    RentalTimesheetPeriod,
    RentalTimesheetProjectSettings,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetStatus,
    RentalWorker,
    WorkerAssignment,
)
from apps.rental_manpower.services.timesheets import month_bounds
from apps.rental_manpower.services.timesheet_policy import (
    DEFAULT_OFF_WEEKDAYS, DEFAULT_OVERTIME_MULTIPLIER, DEFAULT_REGULAR_HOURS_PER_DAY,
    effective_timesheet_policy,
)
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id


def _display(entry):
    if entry.code:
        return entry.code
    return str(int(entry.regular_hours)) if entry.regular_hours == entry.regular_hours.to_integral() else format(entry.regular_hours.normalize(), "f")


_RENTAL_WEEKDAYS = (
    ("sun", "Sunday"), ("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"),
    ("thu", "Thursday"), ("fri", "Friday"), ("sat", "Saturday"),
)
_DEFAULT_OFF_WEEKDAYS = ["fri", "sat"]


def rental_timesheet_settings_payload(*, company, project, period=None, membership=None):
    if project is None:
        off_weekdays = list(DEFAULT_OFF_WEEKDAYS)
        regular_hours = DEFAULT_REGULAR_HOURS_PER_DAY
        multiplier = DEFAULT_OVERTIME_MULTIPLIER
        automatic_overtime = True
        source = "default"
    else:
        policy = effective_timesheet_policy(company=company, project=project, period=period)
        off_weekdays = list(policy.off_weekdays)
        regular_hours = policy.regular_hours_per_day
        multiplier = policy.overtime_multiplier
        automatic_overtime = policy.automatic_overtime
        source = policy.source
    can_edit = bool(membership and membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_EDIT))
    policy_locked = bool(period is not None and period.status != RentalTimesheetStatus.DRAFT)
    can_view_commercial = bool(
        membership is None
        or membership_has_permission(membership, AccessPermission.RENTAL_SETTLEMENTS_VIEW)
        or membership_has_permission(membership, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
    )
    can_view_adjustments = bool(
        membership is None or membership_has_permission(membership, AccessPermission.RENTAL_ADJUSTMENTS_VIEW)
    )
    return {
        "projectId": project_public_id(project) if project else None,
        "offWeekdays": off_weekdays,
        "weekdayOptions": [{"value": key, "label": label} for key, label in _RENTAL_WEEKDAYS],
        "regularHoursPerDay": str(regular_hours),
        "automaticOvertime": automatic_overtime,
        "overtimeMultiplier": str(multiplier),
        "overtimePremiumPercent": str((multiplier - Decimal("1")) * Decimal("100")),
        "policySource": source,
        "policyLocked": policy_locked,
        "canEdit": can_edit,
        "canEditPolicy": bool(can_edit and not policy_locked),
        "canViewCommercial": can_view_commercial,
        "canViewAdjustments": can_view_adjustments,
        "canViewCalculatedResult": bool(can_view_commercial and can_view_adjustments),
        "canViewWorkerIdentity": bool(
            membership is None or membership_has_permission(membership, AccessPermission.RENTAL_WORKERS_VIEW)
        ),
    }


def _period_payload(*, period, project, start: date, end: date, membership=None):
    can_edit = bool(membership and membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_EDIT) and (period is None or period.status == RentalTimesheetStatus.DRAFT))
    can_submit = bool(membership and membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_SUBMIT))
    can_overtime = bool(membership and membership_has_permission(membership, AccessPermission.RENTAL_OVERTIME_EDIT) and (period is None or period.status == RentalTimesheetStatus.DRAFT))
    can_approve = bool(membership and membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_APPROVE))
    status = period.status if period else RentalTimesheetStatus.DRAFT
    next_action = "submit" if status == RentalTimesheetStatus.DRAFT and can_submit else ("approve" if status == RentalTimesheetStatus.SUBMITTED and can_approve else ("lock" if status == RentalTimesheetStatus.APPROVED and can_approve else None))
    return {
        "id": str(period.pk) if period else None,
        "exists": period is not None,
        "period": f"{start:%Y-%m}",
        "label": f"{month_name[start.month]} {start.year}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "projectId": project_public_id(project) if project else None,
        "status": RentalTimesheetStatus(status).label,
        "statusValue": status,
        "revision": period.revision if period else 0,
        "canEdit": can_edit,
        "canSubmit": can_submit,
        "canEditOvertime": can_overtime,
        "canApprove": can_approve,
        "nextAction": next_action,
    }


def _project_worker_queryset(*, company, project, start: date, end: date, query: str = "", supplier_id: str = ""):
    eligible_assignments = (
        WorkerAssignment.objects.for_company(company)
        .filter(
            worker_id=OuterRef("pk"),
            project=project,
            cancelled_at__isnull=True,
            effective_from__lte=end,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
    )
    rows = (
        RentalWorker.objects.for_company(company)
        .filter(deleted_at__isnull=True, archived_at__isnull=True)
        .annotate(_has_period_assignment=Exists(eligible_assignments))
        .filter(_has_period_assignment=True)
        .select_related("supplier")
    )
    q = (query or "").strip()
    if q:
        rows = rows.annotate(_trade_match=Exists(eligible_assignments.filter(trade__icontains=q))).filter(
            Q(worker_number__icontains=q)
            | Q(full_name__icontains=q)
            | Q(supplier__name__icontains=q)
            | Q(_trade_match=True)
        )
    if supplier_id:
        rows = rows.filter(supplier_id=supplier_id)
    return rows.order_by("worker_number", "full_name")


def rental_timesheet_summary(*, company, project, period, start: date, end: date) -> dict[str, object]:
    workers = _project_worker_queryset(company=company, project=project, start=start, end=end)
    worker_count = workers.count()
    supplier_count = workers.order_by().values("supplier_id").distinct().count()
    entry_count = 0
    regular_hours = Decimal("0")
    automatic_overtime_hours = Decimal("0")
    additional_overtime_hours = Decimal("0")
    overtime_hours = Decimal("0")
    overtime_employees = 0
    missing_count = 0
    if period is not None:
        policy = effective_timesheet_policy(company=company, project=project, period=period)
        entry_qs = RentalTimesheetEntry.objects.for_company(company).filter(period=period)
        entry_count = entry_qs.count()
        if policy.automatic_overtime:
            output = DecimalField(max_digits=18, decimal_places=4)
            aggregates = entry_qs.aggregate(
                regular=Sum(
                    Case(
                        When(regular_hours__gt=policy.regular_hours_per_day, then=Value(policy.regular_hours_per_day)),
                        default=F("regular_hours"),
                        output_field=output,
                    )
                ),
                automatic_ot=Sum(
                    Case(
                        When(regular_hours__gt=policy.regular_hours_per_day, then=F("regular_hours") - Value(policy.regular_hours_per_day)),
                        default=Value(Decimal("0")),
                        output_field=output,
                    )
                ),
            )
            regular_hours = aggregates.get("regular") or Decimal("0")
            automatic_overtime_hours = aggregates.get("automatic_ot") or Decimal("0")
            auto_worker_ids = set(
                entry_qs.filter(regular_hours__gt=policy.regular_hours_per_day)
                .values_list("worker_id", flat=True).distinct()
            )
        else:
            regular_hours = entry_qs.aggregate(total=Sum("regular_hours")).get("total") or Decimal("0")
            auto_worker_ids = set()
        overtime_qs = RentalTimesheetOvertime.objects.for_company(company).filter(period=period)
        additional_overtime_hours = overtime_qs.aggregate(total=Sum("hours")).get("total") or Decimal("0")
        overtime_hours = automatic_overtime_hours + additional_overtime_hours
        explicit_worker_ids = set(overtime_qs.values_list("worker_id", flat=True))
        overtime_employees = len(auto_worker_ids | explicit_worker_ids)
        required_days = 0
        for effective_from, effective_to in (
            WorkerAssignment.objects.for_company(company)
            .filter(project=project, cancelled_at__isnull=True, effective_from__lte=end)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
            .values_list("effective_from", "effective_to")
        ):
            segment_start = max(start, effective_from)
            segment_end = min(end, effective_to or end)
            if segment_end >= segment_start:
                required_days += (segment_end - segment_start).days + 1
        missing_count = max(0, required_days - entry_count)
    else:
        required_days = 0
        for effective_from, effective_to in (
            WorkerAssignment.objects.for_company(company)
            .filter(project=project, cancelled_at__isnull=True, effective_from__lte=end)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
            .values_list("effective_from", "effective_to")
        ):
            segment_start = max(start, effective_from)
            segment_end = min(end, effective_to or end)
            if segment_end >= segment_start:
                required_days += (segment_end - segment_start).days + 1
        missing_count = required_days
    return {
        "workerCount": worker_count,
        "supplierCount": supplier_count,
        "entryCount": entry_count,
        "regularHours": str(regular_hours),
        "automaticOvertimeHours": str(automatic_overtime_hours),
        "additionalOvertimeHours": str(additional_overtime_hours),
        "overtimeHours": str(overtime_hours),
        "overtimeEmployees": overtime_employees,
        "missingCount": missing_count,
    }


def _rental_timesheet_adjustment_summary(*, company, project, start: date, worker_ids, membership=None) -> dict[str, dict[str, object]]:
    """Return bounded per-worker adjustment totals for the visible timesheet page.

    Calculated-result previews are intentionally permission-gated. The board returns
    approved and pending (Draft/Review) adjustment buckets separately, plus a current
    preview total that combines both buckets. This lets operators see the projected
    worker payment before approval while Supplier Settlement continues to use Approved
    adjustments only as its financial authority.
    """
    can_view_commercial = bool(
        membership is None
        or membership_has_permission(membership, AccessPermission.RENTAL_SETTLEMENTS_VIEW)
        or membership_has_permission(membership, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
    )
    can_view_adjustments = bool(
        membership is None or membership_has_permission(membership, AccessPermission.RENTAL_ADJUSTMENTS_VIEW)
    )
    if not (can_view_commercial and can_view_adjustments) or not worker_ids:
        return {}

    earning_types = {
        RentalAdjustmentType.BONUS,
        RentalAdjustmentType.REIMBURSEMENT,
        RentalAdjustmentType.OTHER_EARNING,
    }
    result: dict[str, dict[str, object]] = {}
    rows = (
        RentalAdjustment.objects.for_company(company)
        .filter(project=project, period_start=start, worker_id__in=worker_ids)
        .values("worker_id", "status", "adjustment_type")
        .annotate(total=Sum("amount"), row_count=Count("id"))
        .order_by("worker_id", "status", "adjustment_type")
    )
    for row in rows.iterator(chunk_size=256):
        worker_id = str(row["worker_id"])
        bucket = result.setdefault(worker_id, {
            "approvedEarnings": Decimal("0"),
            "approvedDeductions": Decimal("0"),
            "approvedCount": 0,
            "pendingEarnings": Decimal("0"),
            "pendingDeductions": Decimal("0"),
            "pendingCount": 0,
        })
        amount = Decimal(row["total"] or 0)
        row_count = int(row["row_count"] or 0)
        is_earning = row["adjustment_type"] in earning_types
        if row["status"] == RentalAdjustmentStatus.APPROVED:
            bucket["approvedCount"] += row_count
            bucket["approvedEarnings" if is_earning else "approvedDeductions"] += amount
        else:
            bucket["pendingCount"] += row_count
            bucket["pendingEarnings" if is_earning else "pendingDeductions"] += amount

    payload: dict[str, dict[str, object]] = {}
    for worker_id, bucket in result.items():
        approved_earnings = Decimal(bucket["approvedEarnings"])
        approved_deductions = Decimal(bucket["approvedDeductions"])
        pending_earnings = Decimal(bucket["pendingEarnings"])
        pending_deductions = Decimal(bucket["pendingDeductions"])
        preview_earnings = approved_earnings + pending_earnings
        preview_deductions = approved_deductions + pending_deductions
        payload[worker_id] = {
            "approvedEarnings": str(approved_earnings),
            "approvedDeductions": str(approved_deductions),
            "approvedNet": str(approved_earnings - approved_deductions),
            "approvedCount": int(bucket["approvedCount"]),
            "pendingEarnings": str(pending_earnings),
            "pendingDeductions": str(pending_deductions),
            "pendingNet": str(pending_earnings - pending_deductions),
            "pendingCount": int(bucket["pendingCount"]),
            "previewEarnings": str(preview_earnings),
            "previewDeductions": str(preview_deductions),
            "previewNet": str(preview_earnings - preview_deductions),
        }
    return payload


def rental_timesheet_context(
    *, company, project_id, period_start: date, membership=None,
    query: str = "", supplier_id: str = "", page: int | None = None, page_size: int | None = None,
    include_summary: bool = True,
):
    start, end = month_bounds(period_start)
    project = rental_project_for_company(company=company, identifier=project_id) if project_id else None
    if project is not None and membership is not None and not membership_allows_project(membership, project):
        raise PermissionDenied("This Rental project is outside your assigned access scope.")
    period = (
        RentalTimesheetPeriod.objects.for_company(company).select_related("project").filter(project=project, period_start=start).first()
        if project else None
    )
    if not project:
        return {
            "attendanceContract": attendance_contract_payload(ATTENDANCE_WORKSPACE_RENTAL),
            "period": _period_payload(period=period, project=project, start=start, end=end, membership=membership),
            "settings": rental_timesheet_settings_payload(company=company, project=project, period=period, membership=membership),
            "roster": [], "records": {}, "overtime": {}, "adjustmentSummary": {},
            "summary": {"workerCount": 0, "supplierCount": 0, "entryCount": 0, "regularHours": "0", "overtimeHours": "0", "overtimeEmployees": 0, "missingCount": 0},
            "meta": {"count": 0, "page": 1, "pageSize": page_size or 50, "totalPages": 0},
        }

    workers_qs = _project_worker_queryset(
        company=company, project=project, start=start, end=end, query=query, supplier_id=supplier_id,
    )
    if page is not None or page_size is not None:
        page_number = max(1, int(page or 1))
        bounded_size = max(1, min(100, int(page_size or 50)))
        paginator = Paginator(workers_qs, bounded_size)
        page_obj = paginator.get_page(page_number)
        workers = list(page_obj.object_list)
        meta = {
            "count": paginator.count, "page": page_obj.number, "pageSize": bounded_size,
            "totalPages": paginator.num_pages, "query": (query or "").strip(), "supplierId": supplier_id or "",
        }
    else:
        workers = list(workers_qs)
        meta = {"count": len(workers), "page": None, "pageSize": None, "totalPages": None, "query": (query or "").strip(), "supplierId": supplier_id or ""}

    worker_ids = [worker.pk for worker in workers]
    assignments = []
    if worker_ids:
        assignments = list(
            WorkerAssignment.objects.for_company(company)
            .select_related("worker", "worker__supplier", "project")
            .filter(worker_id__in=worker_ids, project=project, cancelled_at__isnull=True, effective_from__lte=end)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
            .order_by("worker__worker_number", "effective_from", "created_at")
        )
    assignments_by_worker: dict[str, list[WorkerAssignment]] = {}
    for assignment in assignments:
        assignments_by_worker.setdefault(str(assignment.worker_id), []).append(assignment)

    entries = list(
        RentalTimesheetEntry.objects.for_company(company).filter(period=period, worker_id__in=worker_ids).select_related("worker", "assignment")
        if period and worker_ids else []
    )
    overtime = list(
        RentalTimesheetOvertime.objects.for_company(company).filter(period=period, worker_id__in=worker_ids).select_related("worker", "assignment")
        if period and worker_ids else []
    )
    records: dict[str, dict[str, str]] = {}
    for entry in entries:
        records.setdefault(str(entry.worker_id), {})[str(entry.work_date.day)] = _display(entry)
    include_commercial = bool(
        membership is None
        or membership_has_permission(membership, AccessPermission.RENTAL_SETTLEMENTS_VIEW)
        or membership_has_permission(membership, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
    )
    ot = {
        str(row.worker_id): {
            "hours": str(row.hours),
            "rate": str(row.rate) if include_commercial else None,
            "trade": row.trade,
            "rateType": row.rate_type,
        }
        for row in overtime
    }
    adjustment_summary = _rental_timesheet_adjustment_summary(
        company=company, project=project, start=start, worker_ids=worker_ids, membership=membership
    )
    include_worker_identity = bool(
        membership is None or membership_has_permission(membership, AccessPermission.RENTAL_WORKERS_VIEW)
    )
    roster = []
    for worker in workers:
        wid = str(worker.pk)
        segments = []
        for assignment in assignments_by_worker.get(wid, []):
            segments.append({
                "id": str(assignment.pk), "kind": "assignment", "projectId": project_public_id(assignment.project),
                "start": assignment.effective_from.isoformat(), "end": assignment.effective_to.isoformat() if assignment.effective_to else None,
                "trade": assignment.trade, "rateType": assignment.get_rate_type_display(), "rateTypeValue": assignment.rate_type,
                "rate": str(assignment.rate) if include_commercial else "Restricted",
                "rateValue": float(assignment.rate) if include_commercial else None,
                "supplierId": str(worker.supplier_id), "supplierName": worker.supplier.name,
            })
        worker_payload = {
            "id": wid, "workerId": worker.worker_number, "workerCode": worker.worker_number, "name": worker.full_name,
            "supplierId": str(worker.supplier_id), "supplierName": worker.supplier.name, "assignments": segments,
            "status": worker.get_status_display(),
        }
        if include_worker_identity:
            worker_payload["nationalId"] = worker.national_id or ""
        roster.append(worker_payload)

    return {
        "attendanceContract": attendance_contract_payload(ATTENDANCE_WORKSPACE_RENTAL),
        "period": _period_payload(period=period, project=project, start=start, end=end, membership=membership),
        "settings": rental_timesheet_settings_payload(company=company, project=project, period=period, membership=membership),
        "roster": roster,
        "records": records,
        "overtime": ot,
        "adjustmentSummary": adjustment_summary,
        **({"summary": rental_timesheet_summary(company=company, project=project, period=period, start=start, end=end)} if include_summary else {}),
        "meta": meta,
    }
