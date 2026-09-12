from __future__ import annotations

from apps.projects.contracts import ProjectStatus
from apps.projects.models import Project
from apps.rental_manpower.project_adapter import rental_projects_for_company, project_public_id

from datetime import timedelta

from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    WorkerAssignment,
)
from apps.rental_manpower.selectors.assignments import assignment_context


def _date_label(value) -> str:
    return value.strftime("%d %b %Y") if value else "—"


def _current_assignment_filter(today):
    return Q(workers__rental_assignments__cancelled_at__isnull=True) & Q(
        workers__rental_assignments__effective_from__lte=today
    ) & (
        Q(workers__rental_assignments__effective_to__isnull=True)
        | Q(workers__rental_assignments__effective_to__gte=today)
    )


def suppliers_for_company(*, company, query: str = "", status: str = "", archived: bool | None = False):
    today = timezone.localdate()
    current_filter = _current_assignment_filter(today)
    queryset = ManpowerSupplier.objects.for_company(company)
    if archived is True:
        queryset = queryset.filter(archived_at__isnull=False)
    elif archived is False:
        queryset = queryset.filter(archived_at__isnull=True)
    if query.strip():
        q = query.strip()
        queryset = queryset.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(contact_person__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(cr_number__icontains=q)
            | Q(vat_number__icontains=q)
            | Q(payment_terms__icontains=q)
            | Q(address__icontains=q)
            | Q(notes__icontains=q)
        )
    if status:
        queryset = queryset.filter(status=status)
    return (
        queryset
        .annotate(
            total_worker_count=Count("workers", distinct=True),
            active_worker_count=Count("workers", filter=Q(workers__status=RentalWorkerStatus.ACTIVE), distinct=True),
            assigned_worker_count=Count(
                "workers",
                filter=Q(workers__status=RentalWorkerStatus.ACTIVE) & current_filter,
                distinct=True,
            ),
            active_project_count=Count(
                "workers__rental_assignments__project",
                filter=Q(workers__status=RentalWorkerStatus.ACTIVE) & current_filter,
                distinct=True,
            ),
        )
        .order_by("code", "name")
    )


def projects_for_company(*, company, query: str = "", status: str = ""):
    today = timezone.localdate()
    current_filter = Q(rental_assignments__cancelled_at__isnull=True) & Q(rental_assignments__effective_from__lte=today) & (
        Q(rental_assignments__effective_to__isnull=True) | Q(rental_assignments__effective_to__gte=today)
    )
    queryset = rental_projects_for_company(company=company, query=query, status=status)
    return (
        queryset.annotate(
            assigned_worker_count=Count(
                "rental_assignments__worker",
                filter=current_filter & Q(rental_assignments__worker__status=RentalWorkerStatus.ACTIVE),
                distinct=True,
            ),
            assigned_supplier_count=Count(
                "rental_assignments__worker__supplier",
                filter=current_filter & Q(rental_assignments__worker__status=RentalWorkerStatus.ACTIVE),
                distinct=True,
            ),
        )
        .order_by("-start_date", "code")
    )


def workers_for_company(*, company, query: str = "", status: str = "", supplier_id=None, archived: bool | None = False):
    assignment_qs = WorkerAssignment.objects.for_company(company).select_related("project", "company__settings").order_by("effective_from", "created_at")
    queryset = RentalWorker.objects.for_company(company).select_related("supplier", "company__settings").prefetch_related(
        Prefetch("rental_assignments", queryset=assignment_qs)
    )
    if archived is True:
        queryset = queryset.filter(archived_at__isnull=False)
    elif archived is False:
        queryset = queryset.filter(archived_at__isnull=True)
    if query.strip():
        q = query.strip()
        queryset = queryset.filter(
            Q(worker_number__icontains=q)
            | Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
            | Q(phone__icontains=q)
            | Q(supplier__code__icontains=q)
            | Q(supplier__name__icontains=q)
            | Q(rental_assignments__trade__icontains=q)
            | Q(rental_assignments__project__code__icontains=q)
            | Q(rental_assignments__project__name__icontains=q)
            | Q(notes__icontains=q)
        ).distinct()
    if status:
        queryset = queryset.filter(status=status)
    if supplier_id:
        queryset = queryset.filter(supplier_id=supplier_id)
    return queryset.order_by("worker_number", "full_name")


def serialize_supplier(supplier: ManpowerSupplier) -> dict[str, object]:
    active_workers = int(getattr(supplier, "active_worker_count", 0))
    total_workers = int(getattr(supplier, "total_worker_count", 0))
    assigned_workers = int(getattr(supplier, "assigned_worker_count", 0))
    return {
        "id": str(supplier.id),
        "code": supplier.code,
        "name": supplier.name,
        "status": "Archived" if supplier.archived_at else supplier.get_status_display(),
        "statusValue": supplier.status,
        "archived": bool(supplier.archived_at),
        "archivedAt": supplier.archived_at.isoformat() if supplier.archived_at else None,
        "archivedReason": supplier.archived_reason,
        "contact": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
        "cr": supplier.cr_number,
        "vat": supplier.vat_number,
        "paymentTerms": supplier.payment_terms,
        "address": supplier.address,
        "notes": supplier.notes,
        "totalWorkers": total_workers,
        "activeWorkers": assigned_workers,
        "availableWorkers": max(0, active_workers - assigned_workers),
        "inactiveWorkers": max(0, total_workers - active_workers),
        "activeProjects": int(getattr(supplier, "active_project_count", 0)),
        "hours": 0,
        "otHours": 0,
        "currentCost": 0,
        "outstanding": 0,
    }


def serialize_project(project: Project) -> dict[str, object]:
    return {
        "id": project_public_id(project),
        "reference": project_public_id(project),
        "code": project.code,
        "name": project.name,
        "client": project.client_name,
        "location": project.location,
        "start": _date_label(project.start_date),
        "startDate": project.start_date.isoformat() if project.start_date else "",
        "end": _date_label(project.end_date),
        "endDate": project.end_date.isoformat() if project.end_date else "",
        "manager": project.manager_name,
        "status": project.get_status_display(),
        "statusValue": project.status,
        "notes": project.notes,
        "rentalWorkers": int(getattr(project, "assigned_worker_count", 0)),
        "suppliers": int(getattr(project, "assigned_supplier_count", 0)),
        "hours": 0,
        "otHours": 0,
        "grossCost": 0,
        "advances": 0,
        "netCost": 0,
    }


def _worker_assignment_snapshot(worker: RentalWorker):
    today = timezone.localdate()
    rows = [row for row in worker.rental_assignments.all() if row.cancelled_at is None]
    current = next(
        (
            row for row in rows
            if row.effective_from <= today and (row.effective_to is None or row.effective_to >= today)
        ),
        None,
    )
    future = next((row for row in rows if row.effective_from > today), None)
    last = next((row for row in reversed(rows) if row.effective_from <= today), None)
    return current, future, last


def _assignment_rate_label(assignment: WorkerAssignment | None, currency: str = "SAR") -> str:
    if assignment is None:
        return "Not assigned"
    value = f"{assignment.rate:,.4f}".rstrip("0").rstrip(".")
    if assignment.rate_type == "monthly":
        return f"Monthly {currency} {value}"
    if assignment.rate_type == "daily":
        return f"{currency} {value}/day"
    return f"{currency} {value}/hr"


def serialize_worker(worker: RentalWorker) -> dict[str, object]:
    current, future, last = _worker_assignment_snapshot(worker)
    master_active = worker.status == RentalWorkerStatus.ACTIVE and not worker.archived_at
    if worker.archived_at:
        display_status = "Archived"
        reference = last
    elif not master_active:
        display_status = "Inactive"
        reference = last
    elif current:
        display_status = "Assigned"
        reference = current
    elif future:
        display_status = "Scheduled"
        reference = future
    else:
        display_status = "Available"
        reference = last

    if display_status == "Assigned" and current:
        project_id = project_public_id(current.project)
        project_name = current.project.name
        since = current.effective_from.isoformat()
    elif display_status == "Scheduled" and future:
        project_id = None
        project_name = "Available / scheduled"
        since = future.effective_from.isoformat()
    else:
        project_id = None
        project_name = "Inactive" if display_status == "Inactive" else "Available / released"
        since = ""
        if last and last.effective_to:
            since = (last.effective_to + timedelta(days=1)).isoformat()

    return {
        "id": str(worker.id),
        "workerCode": worker.worker_number,
        "name": worker.full_name,
        "nationalId": worker.national_id,
        "phone": worker.phone,
        "supplierId": str(worker.supplier_id),
        "supplier": worker.supplier.name,
        "masterStatus": "Archived" if worker.archived_at else worker.get_status_display(),
        "masterStatusValue": worker.status,
        "archived": bool(worker.archived_at),
        "archivedAt": worker.archived_at.isoformat() if worker.archived_at else None,
        "archivedReason": worker.archived_reason,
        "inactiveOn": worker.inactive_on.isoformat() if worker.inactive_on else "",
        "inactiveReason": worker.inactive_reason,
        "status": display_status,
        "projectId": project_id,
        "project": project_name,
        "trade": reference.trade if reference else "Not assigned",
        "rateType": reference.get_rate_type_display() if reference else "",
        "rateTypeValue": reference.rate_type if reference else "",
        "rateValue": float(reference.rate) if reference else None,
        "rate": _assignment_rate_label(reference, worker.company.settings.currency_code),
        "since": since,
        "currentAssignmentId": str(current.pk) if current else None,
        "nextAssignmentId": str(future.pk) if future else None,
        "nextProjectId": project_public_id(future.project) if future else None,
        "nextProject": future.project.name if future else "",
        "notes": worker.notes,
        "source": "Rental worker master",
    }


def rental_master_context(*, company) -> dict[str, object]:
    suppliers = list(suppliers_for_company(company=company, archived=None))
    projects = list(projects_for_company(company=company))
    workers = list(workers_for_company(company=company, archived=None))
    assignments = assignment_context(company=company)
    return {
        "suppliers": [serialize_supplier(item) for item in suppliers],
        "projects": [serialize_project(item) for item in projects],
        "workers": [serialize_worker(item) for item in workers],
        "assignmentsByWorker": assignments["assignmentsByWorker"],
        "assignmentAsOf": assignments["asOf"],
        "assignmentSummary": assignments["summary"],
        "summary": {
            "supplierCount": len(suppliers),
            "activeSupplierCount": sum(item.status == SupplierStatus.ACTIVE for item in suppliers),
            "projectCount": len(projects),
            "activeProjectCount": sum(item.status == ProjectStatus.ACTIVE for item in projects),
            "workerCount": len(workers),
            "activeWorkerCount": sum(item.status == RentalWorkerStatus.ACTIVE for item in workers),
        },
    }
