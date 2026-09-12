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


def suppliers_for_company(*, company, query: str = "", status: str = "", archived: bool | None = False, deleted: bool | None = False):
    today = timezone.localdate()
    current_filter = _current_assignment_filter(today)
    queryset = ManpowerSupplier.objects.for_company(company)
    if deleted is not None:
        queryset = queryset.filter(deleted_at__isnull=not deleted)
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


def workers_for_company(*, company, query: str = "", status: str = "", supplier_id=None, archived: bool | None = False, deleted: bool | None = False):
    assignment_qs = WorkerAssignment.objects.for_company(company).select_related("project", "company__settings").order_by("effective_from", "created_at")
    queryset = RentalWorker.objects.for_company(company).select_related("supplier", "company__settings").prefetch_related(
        Prefetch("rental_assignments", queryset=assignment_qs)
    )
    # Supplier lifecycle is an inherited worker boundary. The worker master is not
    # rewritten, which makes restore exact, but ordinary/Archive/Delete filters
    # behave as a true cascade to the supplier's workers.
    if deleted is False:
        queryset = queryset.filter(deleted_at__isnull=True, supplier__deleted_at__isnull=True)
    elif deleted is True:
        queryset = queryset.filter(Q(deleted_at__isnull=False) | Q(supplier__deleted_at__isnull=False))
    if archived is True:
        queryset = queryset.filter(Q(archived_at__isnull=False) | Q(supplier__archived_at__isnull=False))
    elif archived is False:
        queryset = queryset.filter(archived_at__isnull=True, supplier__archived_at__isnull=True)
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
        "deleted": supplier.deleted_at is not None,
        "deletedAt": supplier.deleted_at.isoformat() if supplier.deleted_at else None,
        "deletionReason": supplier.deletion_reason,
        "purgeAfter": supplier.purge_after.isoformat() if supplier.purge_after else None,
        "contact": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
        "cr": supplier.cr_number,
        "vat": supplier.vat_number,
        "paymentTerms": supplier.payment_terms,
        "address": supplier.address,
        "notes": supplier.notes,
        "inactiveOn": supplier.inactive_on.isoformat() if supplier.inactive_on else "",
        "inactiveReason": supplier.inactive_reason,
        "terminatedOn": supplier.terminated_on.isoformat() if supplier.terminated_on else "",
        "terminationReason": supplier.termination_reason,
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
        "archived": bool(project.archived_at),
        "archivedAt": project.archived_at.isoformat() if project.archived_at else None,
        "archivedReason": project.archived_reason,
        "deleted": bool(project.deleted_at),
        "deletedAt": project.deleted_at.isoformat() if project.deleted_at else None,
        "deletionReason": project.deletion_reason,
        "purgeAfter": project.purge_after.isoformat() if project.purge_after else None,
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
    supplier_archived = bool(worker.supplier.archived_at)
    supplier_deleted = bool(worker.supplier.deleted_at)
    supplier_inactive = worker.supplier.status == SupplierStatus.INACTIVE
    supplier_terminated = worker.supplier.status == SupplierStatus.TERMINATED
    effective_archived = bool(worker.archived_at or supplier_archived)
    effective_deleted = bool(worker.deleted_at or supplier_deleted)
    archive_sources = []
    delete_sources = []
    if supplier_archived:
        archive_sources.append({"type": "supplier", "id": str(worker.supplier_id), "label": worker.supplier.name})
    if supplier_deleted:
        delete_sources.append({"type": "supplier", "id": str(worker.supplier_id), "label": worker.supplier.name})

    master_active = worker.status == RentalWorkerStatus.ACTIVE and worker.supplier.status == SupplierStatus.ACTIVE and not effective_archived and not effective_deleted
    if effective_deleted:
        display_status = "Deleted"
        reference = last
    elif effective_archived:
        display_status = "Archived"
        reference = last
    elif worker.status == RentalWorkerStatus.TERMINATED or supplier_terminated:
        display_status = "Terminated"
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
        if display_status == "Terminated":
            project_name = "Terminated"
        elif display_status == "Inactive":
            project_name = "Inactive"
        elif display_status in {"Archived", "Deleted"}:
            project_name = display_status
        else:
            project_name = "Available / released"
        since = ""
        if last and last.effective_to:
            since = (last.effective_to + timedelta(days=1)).isoformat()

    archived_at = worker.archived_at or (worker.supplier.archived_at if supplier_archived else None)
    deleted_at = worker.deleted_at or (worker.supplier.deleted_at if supplier_deleted else None)
    purge_after = worker.purge_after or (worker.supplier.purge_after if supplier_deleted else None)
    archived_reason = worker.archived_reason if worker.archived_at else (
        "Inherited from archived supplier" if supplier_archived else ""
    )
    deletion_reason = worker.deletion_reason if worker.deleted_at else (
        "Inherited from deleted supplier" if supplier_deleted else ""
    )

    return {
        "id": str(worker.id),
        "workerCode": worker.worker_number,
        "name": worker.full_name,
        "nationalId": worker.national_id,
        "phone": worker.phone,
        "supplierId": str(worker.supplier_id),
        "supplier": worker.supplier.name,
        "masterStatus": "Deleted" if effective_deleted else ("Archived" if effective_archived else ("Terminated" if supplier_terminated else worker.get_status_display())),
        "masterStatusValue": RentalWorkerStatus.TERMINATED if supplier_terminated else worker.status,
        "archived": effective_archived,
        "archivedOwn": bool(worker.archived_at),
        "archivedAt": archived_at.isoformat() if archived_at else None,
        "archivedReason": archived_reason,
        "deleted": effective_deleted,
        "deletedOwn": bool(worker.deleted_at),
        "deletedAt": deleted_at.isoformat() if deleted_at else None,
        "deletionReason": deletion_reason,
        "purgeAfter": purge_after.isoformat() if purge_after else None,
        "cascadeLifecycle": {"archiveSources": archive_sources, "deleteSources": delete_sources},
        "supplierInactive": supplier_inactive,
        "supplierTerminated": supplier_terminated,
        "operationallyStopped": bool(worker.supplier.status != SupplierStatus.ACTIVE or worker.status != RentalWorkerStatus.ACTIVE or effective_archived or effective_deleted),
        "inactiveOn": worker.inactive_on.isoformat() if worker.inactive_on else "",
        "inactiveReason": worker.inactive_reason,
        "terminatedOn": (worker.terminated_on or worker.supplier.terminated_on).isoformat() if (worker.terminated_on or worker.supplier.terminated_on) else "",
        "terminationReason": worker.termination_reason or (f"Inherited from terminated supplier: {worker.supplier.termination_reason}" if supplier_terminated else ""),
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
