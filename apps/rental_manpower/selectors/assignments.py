from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Prefetch, Q, Subquery
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.rental_manpower.models import ReleaseDisposition, RentalWorker, WorkerAssignment
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id
from apps.projects.models import Project


ASSIGNMENT_OBJECT_TYPE = "rental_manpower.WorkerAssignment"


def assignments_for_company(
    *,
    company,
    worker_id=None,
    project_id=None,
    supplier_id=None,
    query: str = "",
):
    queryset = (
        WorkerAssignment.objects.for_company(company)
        .select_related("worker", "worker__supplier", "project", "company__settings")
        .order_by("worker__worker_number", "effective_from", "created_at")
    )
    if worker_id:
        queryset = queryset.filter(worker_id=worker_id)
    if project_id:
        project = rental_project_for_company(company=company, identifier=project_id)
        queryset = queryset.filter(project=project)
    if supplier_id:
        queryset = queryset.filter(worker__supplier_id=supplier_id)
    if query.strip():
        q = query.strip()
        matching_workers = (
            RentalWorker.objects.for_company(company)
            .filter(
                Q(worker_number__icontains=q)
                | Q(full_name__icontains=q)
                | Q(supplier__name__icontains=q)
            )
            .values("pk")
        )
        matching_projects = (
            Project.objects.for_company(company)
            .filter(Q(code__icontains=q) | Q(name__icontains=q))
            .values("pk")
        )
        queryset = queryset.filter(
            Q(worker_id__in=Subquery(matching_workers))
            | Q(project_id__in=Subquery(matching_projects))
            | Q(trade__icontains=q)
            | Q(reason__icontains=q)
            | Q(end_reason__icontains=q)
            | Q(end_notes__icontains=q)
        )
    return queryset


def assignment_on_date(*, company, worker_id, on_date: date):
    return (
        WorkerAssignment.objects.for_company(company)
        .select_related("worker", "worker__supplier", "project", "company__settings")
        .filter(
            worker_id=worker_id,
            effective_from__lte=on_date,
            cancelled_at__isnull=True,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
        .order_by("-effective_from", "-created_at")
        .first()
    )


def current_assignment(*, company, worker_id, as_of: date | None = None):
    return assignment_on_date(company=company, worker_id=worker_id, on_date=as_of or timezone.localdate())


def _rate_number(value: Decimal) -> float:
    return float(value)


def _rate_label(assignment: WorkerAssignment, currency: str = "SAR") -> str:
    value = f"{assignment.rate:,.4f}".rstrip("0").rstrip(".")
    if assignment.rate_type == "monthly":
        return f"Monthly {currency} {value}"
    if assignment.rate_type == "daily":
        return f"{currency} {value}/day"
    return f"{currency} {value}/hr"


def _actor_label(event: AuditEvent | None) -> str:
    if not event:
        return "Audit trail"
    return event.actor_display_name or event.actor_username or "System"


def _audit_maps(*, company, assignments: list[WorkerAssignment]):
    ids = [str(item.pk) for item in assignments]
    created: dict[str, AuditEvent] = {}
    released: dict[str, AuditEvent] = {}
    cancelled: dict[str, AuditEvent] = {}
    if not ids:
        return created, released, cancelled
    for event in AuditEvent.objects.filter(
        company=company,
        object_type=ASSIGNMENT_OBJECT_TYPE,
        object_id__in=ids,
    ).order_by("created_at", "id"):
        if event.action == "rental.assignment.released":
            released[event.object_id] = event
        elif event.action == "rental.assignment.cancelled":
            cancelled[event.object_id] = event
        else:
            created.setdefault(event.object_id, event)
    return created, released, cancelled


def serialize_assignment(
    assignment: WorkerAssignment,
    *,
    as_of: date | None = None,
    audit_event: AuditEvent | None = None,
) -> dict[str, object]:
    today = as_of or timezone.localdate()
    if assignment.cancelled_at:
        status = "Cancelled"
    elif assignment.effective_from > today:
        status = "Scheduled"
    elif assignment.effective_to and assignment.effective_to < today:
        status = "Released" if assignment.release_disposition else "Closed"
    else:
        status = "Active"
    return {
        "id": str(assignment.pk),
        "kind": "assignment",
        "projectId": project_public_id(assignment.project),
        "projectName": assignment.project.name,
        "projectCode": assignment.project.code,
        "projectStatus": assignment.project.get_status_display(),
        "projectStatusValue": assignment.project.status,
        "projectArchived": bool(assignment.project.archived_at),
        "projectDeleted": bool(assignment.project.deleted_at),
        "projectOperational": bool(
            assignment.project.status == assignment.project.Status.ACTIVE
            and not assignment.project.archived_at
            and not assignment.project.deleted_at
        ),
        "trade": assignment.trade,
        "rateType": assignment.get_rate_type_display(),
        "rateTypeValue": assignment.rate_type,
        "rateValue": _rate_number(assignment.rate),
        "rateLabel": _rate_label(assignment, assignment.company.settings.currency_code),
        "start": assignment.effective_from.isoformat(),
        "end": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "status": status,
        "changeType": assignment.get_change_type_display(),
        "changeTypeValue": assignment.change_type,
        "reason": assignment.reason,
        "endReason": assignment.end_reason,
        "endNotes": assignment.end_notes,
        "releaseDisposition": assignment.release_disposition,
        "releaseDispositionLabel": assignment.get_release_disposition_display() if assignment.release_disposition else "",
        "cancelledAt": assignment.cancelled_at.isoformat() if assignment.cancelled_at else None,
        "cancelReason": assignment.cancel_reason,
        "source": "Rental assignment history",
        "actor": _actor_label(audit_event),
        "createdAt": (audit_event.created_at if audit_event else assignment.created_at).isoformat(),
    }


def serialize_release_event(
    assignment: WorkerAssignment,
    *,
    audit_event: AuditEvent | None = None,
) -> dict[str, object] | None:
    if assignment.cancelled_at or not assignment.release_disposition or not assignment.effective_to:
        return None
    start = assignment.effective_to + timedelta(days=1)
    status = "Inactive" if assignment.release_disposition == ReleaseDisposition.INACTIVE else "Available"
    return {
        "id": f"release-{assignment.pk}",
        "kind": "pool",
        "projectId": None,
        "projectName": "Inactive worker" if status == "Inactive" else "Available with supplier",
        "trade": assignment.trade,
        "rateType": assignment.get_rate_type_display(),
        "rateTypeValue": assignment.rate_type,
        "rateValue": _rate_number(assignment.rate),
        "rateLabel": _rate_label(assignment, assignment.company.settings.currency_code),
        "start": start.isoformat(),
        "end": None,
        "status": status,
        "changeType": "Released from project",
        "changeTypeValue": "release",
        "reason": assignment.end_reason or "Released from project",
        "note": assignment.end_notes,
        "source": "Rental assignment history",
        "actor": _actor_label(audit_event),
        "createdAt": (audit_event.created_at if audit_event else assignment.updated_at).isoformat(),
        "releasedAssignmentId": str(assignment.pk),
    }


def serialized_assignment_history(*, company, assignments: list[WorkerAssignment], as_of: date | None = None):
    created_audits, release_audits, cancelled_audits = _audit_maps(company=company, assignments=assignments)
    result: list[dict[str, object]] = []
    for assignment in assignments:
        key = str(assignment.pk)
        result.append(serialize_assignment(
            assignment,
            as_of=as_of,
            audit_event=cancelled_audits.get(key) if assignment.cancelled_at else created_audits.get(key),
        ))
        release = serialize_release_event(assignment, audit_event=release_audits.get(key))
        if release:
            result.append(release)
    return result


def assignment_context(*, company, as_of: date | None = None) -> dict[str, object]:
    today = as_of or timezone.localdate()
    assignments = list(assignments_for_company(company=company))
    by_worker: dict[str, list[WorkerAssignment]] = {}
    for assignment in assignments:
        by_worker.setdefault(str(assignment.worker_id), []).append(assignment)
    return {
        "asOf": today.isoformat(),
        "assignmentsByWorker": {
            worker_id: serialized_assignment_history(company=company, assignments=rows, as_of=today)
            for worker_id, rows in by_worker.items()
        },
        "summary": {
            "assignmentSegments": len(assignments),
            "currentlyAssigned": sum(
                item.cancelled_at is None
                and item.effective_from <= today
                and (item.effective_to is None or item.effective_to >= today)
                for item in assignments
            ),
            "scheduledAssignments": sum(item.cancelled_at is None and item.effective_from > today for item in assignments),
            "cancelledAssignments": sum(item.cancelled_at is not None for item in assignments),
            "openEndedAssignments": sum(item.cancelled_at is None and item.effective_to is None for item in assignments),
        },
    }



def serialized_assignment_activity(*, company, assignments: list[WorkerAssignment], event_filter: str = "") -> list[dict[str, object]]:
    """Serialize a bounded page of assignment segments into UI activity events.

    Assignment Lifecycle used to rebuild every worker's full history in the browser.  This
    serializer keeps the expensive history reasoning on the server and only inspects the
    workers represented by the current page.  A segment can yield its assignment/change
    event and, when released, one release event.
    """
    if not assignments:
        return []

    worker_ids = {item.worker_id for item in assignments}
    history = list(
        WorkerAssignment.objects.for_company(company)
        .filter(worker_id__in=worker_ids)
        .select_related("worker", "worker__supplier", "project", "company__settings")
        .order_by("worker_id", "effective_from", "created_at", "pk")
    )
    previous_by_id: dict[str, WorkerAssignment | None] = {}
    last_by_worker: dict[object, WorkerAssignment] = {}
    for item in history:
        previous_by_id[str(item.pk)] = last_by_worker.get(item.worker_id)
        last_by_worker[item.worker_id] = item

    created_audits, release_audits, cancelled_audits = _audit_maps(company=company, assignments=assignments)
    normalized = (event_filter or "").strip().lower().replace("-", "_").replace(" ", "_")
    result: list[dict[str, object]] = []

    for assignment in assignments:
        key = str(assignment.pk)
        previous = previous_by_id.get(key)
        assignment_event = serialize_assignment(
            assignment,
            audit_event=cancelled_audits.get(key) if assignment.cancelled_at else created_audits.get(key),
        )
        event_type = assignment.get_change_type_display()
        include_assignment = normalized not in {"release"}
        if normalized in {"project_assignment", "assignment"}:
            include_assignment = assignment.change_type == "assignment"
        elif normalized in {"project_transfer", "transfer"}:
            include_assignment = assignment.change_type == "transfer"
        elif normalized in {"trade_change", "trade"}:
            include_assignment = assignment.change_type == "trade_change"
        elif normalized in {"rate_change", "rate"}:
            include_assignment = assignment.change_type == "rate_change"
        elif normalized in {"trade_rate_changes", "trade_rate", "changes"}:
            include_assignment = assignment.change_type in {"trade_change", "rate_change"}

        if include_assignment:
            project_id = project_public_id(assignment.project)
            previous_project_id = project_public_id(previous.project) if previous else None
            from_label = "Supplier pool" if previous is None else "Previous assignment"
            to_label = assignment.project.name
            detail = f"{assignment.trade} · {_rate_label(assignment, assignment.company.settings.currency_code)}"
            if assignment.change_type == "transfer":
                from_label = previous.project.name if previous else "Previous project"
                to_label = assignment.project.name
            elif assignment.change_type == "trade_change":
                from_label = previous.trade if previous else "Previous trade"
                to_label = assignment.trade
                detail = assignment.project.name
            elif assignment.change_type == "rate_change":
                from_label = _rate_label(previous, assignment.company.settings.currency_code) if previous else "Previous rate"
                to_label = _rate_label(assignment, assignment.company.settings.currency_code)
                detail = f"{assignment.project.name} · {assignment.trade}"

            result.append({
                "id": key,
                "worker": {
                    "id": str(assignment.worker_id),
                    "name": assignment.worker.full_name,
                    "workerCode": assignment.worker.worker_number,
                    "supplierId": str(assignment.worker.supplier_id),
                },
                "supplier": {"id": str(assignment.worker.supplier_id), "name": assignment.worker.supplier.name},
                "project": {"id": project_id, "name": assignment.project.name, "code": assignment.project.code},
                "previousProjectId": previous_project_id,
                "type": event_type,
                "effective": assignment.effective_from.isoformat(),
                "from": from_label,
                "to": to_label,
                "detail": detail,
                "reason": assignment.reason or assignment_event.get("source") or "Assignment update",
                "audit": assignment_event.get("actor") or "Audit trail",
                "recordedAt": assignment_event.get("createdAt"),
            })

        if assignment.release_disposition and assignment.effective_to and normalized in {"", "all", "all_activity", "release"}:
            release_event = serialize_release_event(assignment, audit_event=release_audits.get(key))
            if release_event:
                result.append({
                    "id": str(release_event["id"]),
                    "worker": {
                        "id": str(assignment.worker_id),
                        "name": assignment.worker.full_name,
                        "workerCode": assignment.worker.worker_number,
                        "supplierId": str(assignment.worker.supplier_id),
                    },
                    "supplier": {"id": str(assignment.worker.supplier_id), "name": assignment.worker.supplier.name},
                    "project": {"id": project_public_id(assignment.project), "name": assignment.project.name, "code": assignment.project.code},
                    "previousProjectId": project_public_id(assignment.project),
                    "type": "Release",
                    "effective": (assignment.effective_to + timedelta(days=1)).isoformat(),
                    "from": assignment.project.name,
                    "to": "Inactive" if assignment.release_disposition == ReleaseDisposition.INACTIVE else "Available with supplier",
                    "detail": f"{assignment.trade} · {_rate_label(assignment, assignment.company.settings.currency_code)}",
                    "reason": assignment.end_reason or assignment.reason or "Released from project",
                    "audit": release_event.get("actor") or "Audit trail",
                    "recordedAt": release_event.get("createdAt"),
                })

    result.sort(key=lambda row: (str(row.get("effective") or ""), str(row.get("recordedAt") or "")), reverse=True)
    return result
