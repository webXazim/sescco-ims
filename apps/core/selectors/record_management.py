from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.core.trash import TRASH_RETENTION_DAYS, active_trash
from apps.internal_payroll.models import Branch, Department, InternalEmployee
from apps.projects.models import Project
from apps.rental_manpower.models import ManpowerSupplier, RentalWorker


def _archive_entry(*, workspace: str, kind: str, row, code: str, label: str, detail: str = "") -> dict[str, object]:
    return {
        "workspace": workspace,
        "kind": kind,
        "id": str(getattr(row, "reference", None) or row.pk),
        "code": code,
        "label": label,
        "detail": detail,
        "archivedAt": row.archived_at.isoformat() if row.archived_at else None,
        "archiveReason": row.archived_reason,
    }


def _trash_entry(*, workspace: str, kind: str, row, code: str, label: str, detail: str = "") -> dict[str, object]:
    return {
        "workspace": workspace,
        "kind": kind,
        "id": str(getattr(row, "reference", None) or row.pk),
        "code": code,
        "label": label,
        "detail": detail,
        "deletedAt": row.deleted_at.isoformat() if row.deleted_at else None,
        "deletionReason": row.deletion_reason,
        "purgeAfter": row.purge_after.isoformat() if row.purge_after else None,
        "archived": bool(getattr(row, "archived_at", None)),
    }



def _organization_impact(row) -> str:
    count = row.employee_assignments.filter(effective_to__isnull=True, employee__deleted_at__isnull=True).count()
    noun = "employee" if count == 1 else "employees"
    return f"{count} current {noun} follow this lifecycle"


def _supplier_impact(row) -> str:
    count = row.workers.filter(deleted_at__isnull=True).count()
    noun = "worker" if count == 1 else "workers"
    return f"{count} {noun} follow this lifecycle"


def _project_impact(row) -> str:
    stock = row.stock_items.filter(current_quantity__gt=0).count()
    today = timezone.localdate()
    assignments = row.rental_assignments.filter(cancelled_at__isnull=True).filter(
        Q(effective_to__isnull=True) | Q(effective_to__gte=today)
    ).count() if hasattr(row, "rental_assignments") else 0
    return f"{stock} stock balances · {assignments} current rental assignments follow this lifecycle"

def record_management_context(*, company, include_internal: bool, include_rental: bool) -> dict[str, object]:
    archive: list[dict[str, object]] = []
    trash: list[dict[str, object]] = []

    if include_internal:
        for row in Branch.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name"):
            archive.append(_archive_entry(workspace="internal", kind="branch", row=row, code=row.code, label=row.name, detail=f"{row.get_kind_display()} · {_organization_impact(row)}"))
        for row in Department.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name"):
            archive.append(_archive_entry(workspace="internal", kind="department", row=row, code=row.code, label=row.name, detail=f"Department · {_organization_impact(row)}"))
        for row in InternalEmployee.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("full_name"):
            archive.append(_archive_entry(workspace="internal", kind="employee", row=row, code=row.employee_number, label=row.full_name, detail=row.get_status_display()))

        for row in active_trash(Branch.objects.for_company(company)).order_by("name"):
            trash.append(_trash_entry(workspace="internal", kind="branch", row=row, code=row.code, label=row.name, detail=f"{row.get_kind_display()} · {_organization_impact(row)}"))
        for row in active_trash(Department.objects.for_company(company)).order_by("name"):
            trash.append(_trash_entry(workspace="internal", kind="department", row=row, code=row.code, label=row.name, detail=f"Department · {_organization_impact(row)}"))
        for row in active_trash(InternalEmployee.objects.for_company(company)).order_by("full_name"):
            trash.append(_trash_entry(workspace="internal", kind="employee", row=row, code=row.employee_number, label=row.full_name, detail=row.get_status_display()))

    if include_rental:
        for row in ManpowerSupplier.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name"):
            archive.append(_archive_entry(workspace="rental", kind="supplier", row=row, code=row.code, label=row.name, detail=f"Manpower supplier · {_supplier_impact(row)}"))
        for row in RentalWorker.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("full_name"):
            archive.append(_archive_entry(workspace="rental", kind="worker", row=row, code=row.worker_number, label=row.full_name, detail=row.supplier.name))
        for row in Project.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("code"):
            archive.append(_archive_entry(workspace="rental", kind="project", row=row, code=row.code, label=row.name, detail=f"{row.location or row.client_name or 'Project'} · {_project_impact(row)}"))

        for row in active_trash(ManpowerSupplier.objects.for_company(company)).order_by("name"):
            trash.append(_trash_entry(workspace="rental", kind="supplier", row=row, code=row.code, label=row.name, detail=f"Manpower supplier · {_supplier_impact(row)}"))
        for row in active_trash(RentalWorker.objects.for_company(company)).select_related("supplier").order_by("full_name"):
            trash.append(_trash_entry(workspace="rental", kind="worker", row=row, code=row.worker_number, label=row.full_name, detail=row.supplier.name))
        for row in active_trash(Project.objects.for_company(company)).order_by("code"):
            trash.append(_trash_entry(workspace="rental", kind="project", row=row, code=row.code, label=row.name, detail=f"{row.location or row.client_name or 'Project'} · {_project_impact(row)}"))

    return {
        "archive": archive,
        "trash": trash,
        "retentionDays": TRASH_RETENTION_DAYS,
    }
