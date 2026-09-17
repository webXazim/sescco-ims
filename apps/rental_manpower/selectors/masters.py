from __future__ import annotations

from apps.projects.contracts import ProjectStatus
from apps.projects.models import Project
from apps.rental_manpower.project_adapter import rental_projects_for_company, project_public_id

from datetime import date, timedelta

from django.db.models import CharField, Count, Exists, F, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission, restrict_projects

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


def suppliers_for_company(
    *, company, query: str = "", status: str = "", archived: bool | None = False, deleted: bool | None = False,
    project_id=None, payment_terms: str = "", workforce: str = "",
):
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
    if payment_terms:
        queryset = queryset.filter(payment_terms=payment_terms)
    if project_id:
        queryset = queryset.filter(
            workers__rental_assignments__project_id=project_id,
            workers__rental_assignments__cancelled_at__isnull=True,
            workers__rental_assignments__effective_from__lte=today,
        ).filter(
            Q(workers__rental_assignments__effective_to__isnull=True)
            | Q(workers__rental_assignments__effective_to__gte=today)
        )
    queryset = (
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
    )
    if workforce == "assigned":
        queryset = queryset.filter(assigned_worker_count__gt=0)
    elif workforce == "available":
        queryset = queryset.filter(active_worker_count__gt=F("assigned_worker_count"))
    elif workforce == "none":
        queryset = queryset.filter(active_worker_count=0)
    return queryset.order_by("code", "name")


def projects_for_company(
    *, company, query: str = "", status: str = "", client: str | None = None,
    manager: str | None = None, supplier_id=None, membership=None,
):
    today = timezone.localdate()
    current_filter = Q(rental_assignments__cancelled_at__isnull=True) & Q(rental_assignments__effective_from__lte=today) & (
        Q(rental_assignments__effective_to__isnull=True) | Q(rental_assignments__effective_to__gte=today)
    )
    queryset = rental_projects_for_company(company=company, query=query, status=status)
    if membership is not None:
        queryset = restrict_projects(queryset, membership)
    if client is not None:
        queryset = queryset.filter(client_name=client)
    if manager is not None:
        queryset = queryset.filter(manager_name=manager)
    if supplier_id:
        queryset = queryset.filter(
            rental_assignments__worker__supplier_id=supplier_id,
            rental_assignments__cancelled_at__isnull=True,
            rental_assignments__effective_from__lte=today,
        ).filter(
            Q(rental_assignments__effective_to__isnull=True) | Q(rental_assignments__effective_to__gte=today)
        ).distinct()
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


def workers_for_company(
    *, company, query: str = "", status: str = "", supplier_id=None, archived: bool | None = False,
    deleted: bool | None = False, operational_status: str = "", project_id=None, trade: str = "", rate_type: str = "",
    membership=None,
):
    assignment_qs = WorkerAssignment.objects.for_company(company).select_related("project", "company__settings").order_by("effective_from", "created_at")
    if membership is not None:
        assignment_qs = restrict_projects(assignment_qs, membership, field="project_id")
    queryset = RentalWorker.objects.for_company(company).select_related("supplier", "company__settings").prefetch_related(
        Prefetch("rental_assignments", queryset=assignment_qs)
    )
    if membership is not None and membership.project_scope_mode != "all":
        # Include current and scheduled workers for selected projects, but never expose
        # the supplier-wide unassigned pool to a project-scoped supervisor.
        scoped_assignments = restrict_projects(
            WorkerAssignment.objects.for_company(company).filter(
                worker_id=OuterRef("pk"), cancelled_at__isnull=True
            ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=timezone.localdate())),
            membership,
            field="project_id",
        )
        queryset = queryset.annotate(_project_scope_match=Exists(scoped_assignments)).filter(_project_scope_match=True)
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
        assignment_search = WorkerAssignment.objects.for_company(company).filter(
            worker_id=OuterRef("pk")
        ).filter(
            Q(trade__icontains=q)
            | Q(project__code__icontains=q)
            | Q(project__name__icontains=q)
        )
        queryset = queryset.annotate(_assignment_search_match=Exists(assignment_search)).filter(
            Q(worker_number__icontains=q)
            | Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
            | Q(phone__icontains=q)
            | Q(supplier__code__icontains=q)
            | Q(supplier__name__icontains=q)
            | Q(notes__icontains=q)
            | Q(_assignment_search_match=True)
        )
    if status:
        queryset = queryset.filter(status=status)
    if supplier_id:
        queryset = queryset.filter(supplier_id=supplier_id)

    today = timezone.localdate()
    assignment_base = WorkerAssignment.objects.for_company(company).filter(worker_id=OuterRef("pk"), cancelled_at__isnull=True)
    current_assignments = assignment_base.filter(effective_from__lte=today).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today)).order_by("-effective_from", "-created_at")
    future_assignments = assignment_base.filter(effective_from__gt=today).order_by("effective_from", "created_at")
    last_assignments = assignment_base.filter(effective_from__lte=today).order_by("-effective_from", "-created_at")
    queryset = queryset.annotate(
        _has_current_assignment=Exists(current_assignments),
        _has_future_assignment=Exists(future_assignments),
        _display_trade=Coalesce(
            Subquery(current_assignments.values("trade")[:1], output_field=CharField()),
            Subquery(future_assignments.values("trade")[:1], output_field=CharField()),
            Subquery(last_assignments.values("trade")[:1], output_field=CharField()),
            Value(""),
        ),
        _display_rate_type=Coalesce(
            Subquery(current_assignments.values("rate_type")[:1], output_field=CharField()),
            Subquery(future_assignments.values("rate_type")[:1], output_field=CharField()),
            Subquery(last_assignments.values("rate_type")[:1], output_field=CharField()),
            Value(""),
        ),
    )
    if operational_status:
        normalized = operational_status.strip().lower().replace(" ", "_")
        if normalized == "assigned":
            queryset = queryset.filter(status=RentalWorkerStatus.ACTIVE, supplier__status=SupplierStatus.ACTIVE, _has_current_assignment=True)
        elif normalized == "scheduled":
            queryset = queryset.filter(status=RentalWorkerStatus.ACTIVE, supplier__status=SupplierStatus.ACTIVE, _has_current_assignment=False, _has_future_assignment=True)
        elif normalized == "available":
            queryset = queryset.filter(status=RentalWorkerStatus.ACTIVE, supplier__status=SupplierStatus.ACTIVE, _has_current_assignment=False, _has_future_assignment=False)
        elif normalized == "inactive":
            queryset = queryset.filter(Q(status=RentalWorkerStatus.INACTIVE) | Q(supplier__status=SupplierStatus.INACTIVE))
        elif normalized == "terminated":
            queryset = queryset.filter(Q(status=RentalWorkerStatus.TERMINATED) | Q(supplier__status=SupplierStatus.TERMINATED))
        elif normalized == "pool":
            queryset = queryset.filter(
                Q(status=RentalWorkerStatus.ACTIVE, supplier__status=SupplierStatus.ACTIVE, _has_current_assignment=False, _has_future_assignment=False)
                | Q(status=RentalWorkerStatus.INACTIVE)
                | Q(supplier__status=SupplierStatus.INACTIVE)
            )
        elif normalized not in {"", "all", "archived"}:
            raise ValueError("Unknown rental worker operational status.")
    if project_id == "unassigned":
        queryset = queryset.filter(_has_current_assignment=False)
    elif project_id:
        queryset = queryset.annotate(
            _current_project_match=Exists(current_assignments.filter(project_id=project_id))
        ).filter(_current_project_match=True)
    if trade:
        queryset = queryset.filter(_display_trade=trade)
    if rate_type:
        queryset = queryset.filter(_display_rate_type=rate_type)
    return queryset.order_by("worker_number", "full_name")



def worker_directory_summary(*, company, membership=None) -> dict[str, int]:
    """Authoritative unfiltered worker-master counts for the current access scope.

    The browser bootstrap is intentionally bounded, so page KPIs must never be
    derived from the bootstrap array.  These counts are calculated from the same
    effective-dated assignment rules used by the directory itself.
    """
    base = workers_for_company(company=company, archived=False, membership=membership).order_by()
    active_base = base.filter(status=RentalWorkerStatus.ACTIVE, supplier__status=SupplierStatus.ACTIVE)
    assigned = active_base.filter(_has_current_assignment=True).count()
    scheduled = active_base.filter(_has_current_assignment=False, _has_future_assignment=True).count()
    available = active_base.filter(_has_current_assignment=False, _has_future_assignment=False).count()
    inactive = base.filter(Q(status=RentalWorkerStatus.INACTIVE) | Q(supplier__status=SupplierStatus.INACTIVE)).count()
    terminated = base.filter(Q(status=RentalWorkerStatus.TERMINATED) | Q(supplier__status=SupplierStatus.TERMINATED)).count()
    archived = workers_for_company(company=company, archived=True, membership=membership).order_by().count()
    active_suppliers = active_base.values('supplier_id').distinct().count()

    today = timezone.localdate()
    assignment_rows = WorkerAssignment.objects.for_company(company).filter(
        worker__deleted_at__isnull=True,
        worker__supplier__deleted_at__isnull=True,
        worker__archived_at__isnull=True,
        worker__supplier__archived_at__isnull=True,
        worker__status=RentalWorkerStatus.ACTIVE,
        worker__supplier__status=SupplierStatus.ACTIVE,
        cancelled_at__isnull=True,
        effective_from__lte=today,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
    if membership is not None:
        assignment_rows = restrict_projects(assignment_rows, membership, field='project_id')
    active_projects = assignment_rows.values('project_id').distinct().count()

    return {
        'total': base.count(),
        'activeMasters': assigned + scheduled + available,
        'assigned': assigned,
        'scheduled': scheduled,
        'available': available,
        'inactive': inactive,
        'terminated': terminated,
        'archived': archived,
        'activeSuppliers': active_suppliers,
        'activeProjects': active_projects,
    }

def serialize_supplier(supplier: ManpowerSupplier, financial: dict[str, object] | None = None) -> dict[str, object]:
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
        "hours": financial.get("hours") if financial else None,
        "otHours": financial.get("otHours") if financial else None,
        "currentCost": financial.get("net") if financial else None,
        "outstanding": financial.get("outstanding") if financial else None,
    }


def serialize_project(project: Project, financial: dict[str, object] | None = None) -> dict[str, object]:
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
        "hours": financial.get("hours") if financial else None,
        "otHours": financial.get("otHours") if financial else None,
        "grossCost": financial.get("gross") if financial else None,
        "advances": financial.get("advances") if financial else None,
        "netCost": financial.get("net") if financial else None,
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


def serialize_worker(worker: RentalWorker, *, include_commercial: bool = True) -> dict[str, object]:
    current, future, last = _worker_assignment_snapshot(worker)
    supplier_archived = bool(worker.supplier.archived_at)
    supplier_deleted = bool(worker.supplier.deleted_at)
    supplier_inactive = worker.supplier.status == SupplierStatus.INACTIVE
    supplier_terminated = worker.supplier.status == SupplierStatus.TERMINATED
    effective_archived = bool(worker.archived_at or supplier_archived)
    effective_deleted = bool(worker.deleted_at or supplier_deleted)

    # A project is not the lifecycle parent of the permanent worker master, so
    # project Archive/Delete must never move the worker itself to Archive/Delete.
    # It *is* an inherited operational boundary for the current assignment.  Keep
    # the effective-dated assignment intact and publish the project boundary so
    # the UI can stop project-local actions while still allowing transfer/release.
    assignment_project = current.project if current else None
    assignment_project_archived = bool(assignment_project and assignment_project.archived_at)
    assignment_project_deleted = bool(assignment_project and assignment_project.deleted_at)
    assignment_project_active = bool(
        assignment_project
        and assignment_project.status == Project.Status.ACTIVE
        and not assignment_project_archived
        and not assignment_project_deleted
    )

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
        "assignmentLifecycle": {
            "projectId": project_public_id(assignment_project) if assignment_project else None,
            "projectStatus": assignment_project.get_status_display() if assignment_project else "",
            "projectStatusValue": assignment_project.status if assignment_project else "",
            "projectArchived": assignment_project_archived,
            "projectDeleted": assignment_project_deleted,
            "operational": assignment_project_active if assignment_project else True,
        },
        "supplierInactive": supplier_inactive,
        "supplierTerminated": supplier_terminated,
        "operationallyStopped": bool(
            worker.supplier.status != SupplierStatus.ACTIVE
            or worker.status != RentalWorkerStatus.ACTIVE
            or effective_archived
            or effective_deleted
            or (assignment_project is not None and not assignment_project_active)
        ),
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
        "rateValue": (float(reference.rate) if reference else None) if include_commercial else None,
        "rate": _assignment_rate_label(reference, worker.company.settings.currency_code) if include_commercial else "Restricted",
        "since": since,
        "currentAssignmentId": str(current.pk) if current else None,
        "nextAssignmentId": str(future.pk) if future else None,
        "nextProjectId": project_public_id(future.project) if future else None,
        "nextProject": future.project.name if future else "",
        "notes": worker.notes,
        "source": "Rental worker master",
    }


def rental_master_context(
    *,
    company,
    period_start: date | None = None,
    worker_limit: int | None = None,
    include_assignments: bool = True,
    membership=None,
) -> dict[str, object]:
    """Return the Rental master bootstrap.

    The production shell uses a bounded worker bootstrap and does not embed complete
    assignment histories. Server-paged Workforce/Assignment/Timesheet APIs remain the
    authority for large collections.
    """
    from apps.core.payroll_attendance_contract import ATTENDANCE_WORKSPACE_RENTAL, attendance_contract_payload
    from apps.rental_manpower.selectors.settlements import rental_financial_metrics_for_period

    period_start = (period_start or timezone.localdate()).replace(day=1)
    can_supplier_view = bool(membership is None or membership_has_permission(membership, AccessPermission.RENTAL_SUPPLIERS_VIEW))
    can_finance = bool(membership is None or membership_has_permission(membership, AccessPermission.RENTAL_SETTLEMENTS_VIEW))
    can_commercial = bool(membership is None or can_finance or membership_has_permission(membership, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE))
    suppliers = list(suppliers_for_company(company=company, archived=None)) if can_supplier_view else []
    projects = list(projects_for_company(company=company, membership=membership))
    worker_qs = workers_for_company(company=company, archived=None, membership=membership)
    total_worker_count = worker_qs.count()
    active_worker_count = worker_qs.filter(status=RentalWorkerStatus.ACTIVE).count()
    workers = list(worker_qs[:worker_limit] if worker_limit else worker_qs)
    assignments = assignment_context(company=company) if include_assignments else {
        "assignmentsByWorker": {},
        "asOf": timezone.localdate().isoformat(),
        "summary": {},
    }
    financial_metrics = (
        rental_financial_metrics_for_period(company=company, period_start=period_start)
        if can_finance else {"suppliers": {}, "projects": {}, "totals": {}}
    )
    supplier_metrics = financial_metrics.get("suppliers", {})
    project_metrics = financial_metrics.get("projects", {})
    if can_supplier_view:
        assigned_count = sum(int(getattr(item, "assigned_worker_count", 0)) for item in suppliers)
        available_count = sum(max(0, int(getattr(item, "active_worker_count", 0)) - int(getattr(item, "assigned_worker_count", 0))) for item in suppliers)
    else:
        # A scoped Supervisor has no supplier-finance directory, but the workforce KPI
        # must still reflect the allowed project roster rather than collapsing to zero.
        assigned_count = worker_qs.filter(_has_current_assignment=True).count()
        available_count = 0
    return {
        "attendanceContract": attendance_contract_payload(ATTENDANCE_WORKSPACE_RENTAL),
        "financialPeriod": period_start.strftime("%B %Y"),
        "financialPeriodKey": f"{period_start:%Y-%m}",
        "financialMetrics": financial_metrics,
        "suppliers": [serialize_supplier(item, supplier_metrics.get(str(item.pk))) for item in suppliers],
        "projects": [serialize_project(item, project_metrics.get(project_public_id(item))) for item in projects],
        "workers": [serialize_worker(item, include_commercial=can_commercial) for item in workers],
        "assignmentsByWorker": assignments["assignmentsByWorker"],
        "assignmentAsOf": assignments["asOf"],
        "assignmentSummary": assignments["summary"],
        "bootstrapComplete": worker_limit is None or len(workers) >= total_worker_count,
        "summary": {
            "supplierCount": len(suppliers),
            "activeSupplierCount": sum(item.status == SupplierStatus.ACTIVE for item in suppliers),
            "projectCount": len(projects),
            "activeProjectCount": sum(item.status == ProjectStatus.ACTIVE for item in projects),
            "workerCount": total_worker_count,
            "activeWorkerCount": active_worker_count,
            "assignedWorkerCount": assigned_count,
            "availableWorkerCount": available_count,
            "bootstrapWorkerCount": len(workers),
        },
    }
