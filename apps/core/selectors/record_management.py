from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.accounts.access_policy import branch_scope_ids, project_scope_ids
from apps.core.trash import TRASH_RETENTION_DAYS, active_cascade_child_count, active_cascade_child_ids, active_trash
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
    if row.deleted_at:
        count = active_cascade_child_count(root=row, child_type="internal_payroll.InternalEmployee")
    else:
        count = row.employee_assignments.filter(effective_to__isnull=True, employee__deleted_at__isnull=True).count()
    noun = "employee" if count == 1 else "employees"
    return f"{count} current {noun} follow this lifecycle"


def _supplier_impact(row) -> str:
    if row.deleted_at:
        count = active_cascade_child_count(root=row, child_type="rental_manpower.RentalWorker")
    else:
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

RECORD_PAGE_SIZES = {25, 50, 100}


def _record_page_size(value: object) -> int:
    try:
        size = int(value or 50)
    except (TypeError, ValueError):
        size = 50
    return size if size in RECORD_PAGE_SIZES else 50


def _record_page_number(value: object) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _record_groups(*, company, workspace: str, bucket: str, query: str, membership=None):
    groups = []
    q = str(query or "").strip()
    if workspace == "internal":
        if bucket == "archive":
            branch_qs = Branch.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name")
            dept_qs = Department.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name")
            emp_qs = InternalEmployee.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("full_name")
        else:
            cascade_ids = active_cascade_child_ids(company=company, child_type="internal_payroll.InternalEmployee")
            branch_qs = active_trash(Branch.objects.for_company(company)).order_by("name")
            dept_qs = active_trash(Department.objects.for_company(company)).order_by("name")
            emp_qs = active_trash(InternalEmployee.objects.for_company(company)).exclude(pk__in=cascade_ids).order_by("full_name")
        branch_ids = branch_scope_ids(membership) if membership is not None else None
        if branch_ids is not None:
            if not branch_ids:
                branch_qs = branch_qs.none(); dept_qs = dept_qs.none(); emp_qs = emp_qs.none()
            else:
                branch_qs = branch_qs.filter(pk__in=branch_ids)
                # Departments are company-wide masters rather than Branch-owned records;
                # branch-restricted recovery views fail closed instead of leaking names/counts.
                dept_qs = dept_qs.none()
                emp_qs = emp_qs.filter(
                    organization_assignments__effective_to__isnull=True,
                    organization_assignments__branch_id__in=branch_ids,
                ).distinct()
        if q:
            branch_qs = branch_qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
            dept_qs = dept_qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
            emp_qs = emp_qs.filter(Q(employee_number__icontains=q) | Q(full_name__icontains=q))
        groups.extend([
            ("branch", branch_qs), ("department", dept_qs), ("employee", emp_qs),
        ])
    elif workspace == "rental":
        if bucket == "archive":
            supplier_qs = ManpowerSupplier.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("name")
            worker_qs = RentalWorker.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).select_related("supplier").order_by("full_name")
            project_qs = Project.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).order_by("code")
        else:
            cascade_ids = active_cascade_child_ids(company=company, child_type="rental_manpower.RentalWorker")
            supplier_qs = active_trash(ManpowerSupplier.objects.for_company(company)).order_by("name")
            worker_qs = active_trash(RentalWorker.objects.for_company(company)).exclude(pk__in=cascade_ids).select_related("supplier").order_by("full_name")
            project_qs = active_trash(Project.objects.for_company(company)).order_by("code")
        project_ids = project_scope_ids(membership) if membership is not None else None
        if project_ids is not None:
            if not project_ids:
                supplier_qs = supplier_qs.none(); worker_qs = worker_qs.none(); project_qs = project_qs.none()
            else:
                project_qs = project_qs.filter(pk__in=project_ids)
                worker_qs = worker_qs.filter(rental_assignments__project_id__in=project_ids).distinct()
                # Supplier lifecycle is cross-project. A project-scoped actor must not infer
                # the company supplier master through Archive/Delete recovery.
                supplier_qs = supplier_qs.none()
        if q:
            supplier_qs = supplier_qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
            worker_qs = worker_qs.filter(Q(worker_number__icontains=q) | Q(full_name__icontains=q) | Q(supplier__name__icontains=q))
            project_qs = project_qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(location__icontains=q) | Q(client_name__icontains=q))
        groups.extend([
            ("supplier", supplier_qs), ("worker", worker_qs), ("project", project_qs),
        ])
    else:
        raise ValueError("Workspace must be internal or rental.")
    return groups


def _record_entry(*, workspace: str, bucket: str, kind: str, row):
    is_trash = bucket == "trash"
    entry = _trash_entry if is_trash else _archive_entry
    if kind == "branch":
        return entry(workspace=workspace, kind=kind, row=row, code=row.code, label=row.name, detail=f"{row.get_kind_display()} · {_organization_impact(row)}")
    if kind == "department":
        return entry(workspace=workspace, kind=kind, row=row, code=row.code, label=row.name, detail=f"Department · {_organization_impact(row)}")
    if kind == "employee":
        return entry(workspace=workspace, kind=kind, row=row, code=row.employee_number, label=row.full_name, detail=row.get_status_display())
    if kind == "supplier":
        return entry(workspace=workspace, kind=kind, row=row, code=row.code, label=row.name, detail=f"Manpower supplier · {_supplier_impact(row)}")
    if kind == "worker":
        return entry(workspace=workspace, kind=kind, row=row, code=row.worker_number, label=row.full_name, detail=row.supplier.name)
    if kind == "project":
        return entry(workspace=workspace, kind=kind, row=row, code=row.code, label=row.name, detail=f"{row.location or row.client_name or 'Project'} · {_project_impact(row)}")
    raise ValueError("Unknown record-management kind.")


def record_management_page_context(*, company, workspace: str, bucket: str, page: object = 1, page_size: object = 50, query: str = "", membership=None) -> dict[str, object]:
    bucket = str(bucket or "archive").strip().lower()
    if bucket not in {"archive", "trash"}:
        raise ValueError("Record bucket must be archive or trash.")
    groups = _record_groups(company=company, workspace=workspace, bucket=bucket, query=query, membership=membership)
    counts = [(kind, qs, qs.count()) for kind, qs in groups]
    count = sum(item[2] for item in counts)
    size = _record_page_size(page_size)
    total_pages = max(1, (count + size - 1) // size)
    page_number = min(_record_page_number(page), total_pages)
    offset = (page_number - 1) * size
    remaining = size
    rows = []
    cursor = offset
    for kind, qs, group_count in counts:
        if remaining <= 0:
            break
        if cursor >= group_count:
            cursor -= group_count
            continue
        take = min(remaining, group_count - cursor)
        for row in qs[cursor:cursor + take]:
            rows.append(_record_entry(workspace=workspace, bucket=bucket, kind=kind, row=row))
        remaining -= take
        cursor = 0
    return {
        "surface": "record_management_page",
        "bucket": bucket,
        "records": rows,
        "retentionDays": TRASH_RETENTION_DAYS,
        "meta": {
            "count": count, "page": page_number, "pageSize": size, "totalPages": total_pages,
            "rangeStart": offset + 1 if count else 0, "rangeEnd": min(count, offset + size),
        },
    }


def record_management_context(*, company, include_internal: bool, include_rental: bool) -> dict[str, object]:
    # Upgrade 1.0.76: Archive/Delete registers are loaded only when those pages are opened.
    return {"archive": [], "trash": [], "retentionDays": TRASH_RETENTION_DAYS, "deferred": True}
