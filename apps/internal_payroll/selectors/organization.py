from __future__ import annotations

from django.db.models import Exists, OuterRef, Prefetch, Q, QuerySet

from apps.core.models import Company
from apps.core.services.lifecycle import lifecycle_capabilities
from apps.internal_payroll.models import Branch, Department, EmployeeOrganizationAssignment, InternalEmployee


def branches_for_company(*, company: Company, query: str = "", active: bool | None = None, archived: bool | None = False, deleted: bool | None = False) -> QuerySet[Branch]:
    rows = Branch.objects.for_company(company)
    if deleted is not None:
        rows = rows.filter(deleted_at__isnull=not deleted)
    if archived is not None:
        rows = rows.filter(archived_at__isnull=not archived)
    if active is not None:
        rows = rows.filter(is_active=active)
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(location__icontains=query)
            | Q(address__icontains=query)
            | Q(manager_name__icontains=query)
        )
    return rows.order_by("code", "name")


def departments_for_company(*, company: Company, query: str = "", active: bool | None = None, archived: bool | None = False, deleted: bool | None = False) -> QuerySet[Department]:
    rows = Department.objects.for_company(company)
    if deleted is not None:
        rows = rows.filter(deleted_at__isnull=not deleted)
    if archived is not None:
        rows = rows.filter(archived_at__isnull=not archived)
    if active is not None:
        rows = rows.filter(is_active=active)
    query = query.strip()
    if query:
        rows = rows.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(notes__icontains=query))
    return rows.order_by("code", "name")


def employees_for_company(
    *,
    company: Company,
    query: str = "",
    status: str = "",
    branch_id=None,
    department_id=None,
    archived: bool | None = None,
    deleted: bool | None = False,
) -> QuerySet[InternalEmployee]:
    assignment_history = EmployeeOrganizationAssignment.objects.for_company(company).select_related(
        "branch", "department"
    ).order_by("-effective_from", "-created_at")
    current_assignment = EmployeeOrganizationAssignment.objects.for_company(company).filter(
        employee_id=OuterRef("pk"), effective_to__isnull=True
    )
    inherited_deleted = current_assignment.filter(
        Q(branch__deleted_at__isnull=False) | Q(department__deleted_at__isnull=False)
    )
    inherited_archived = current_assignment.filter(
        Q(branch__archived_at__isnull=False) | Q(department__archived_at__isnull=False)
    )
    rows = (
        InternalEmployee.objects.for_company(company)
        .prefetch_related(Prefetch("organization_assignments", queryset=assignment_history, to_attr="organization_history"))
        .annotate(
            _inherited_deleted=Exists(inherited_deleted),
            _inherited_archived=Exists(inherited_archived),
        )
    )
    if deleted is False:
        rows = rows.filter(deleted_at__isnull=True, _inherited_deleted=False)
    elif deleted is True:
        rows = rows.filter(Q(deleted_at__isnull=False) | Q(_inherited_deleted=True))
    if archived is False:
        rows = rows.filter(archived_at__isnull=True, _inherited_archived=False)
    elif archived is True:
        rows = rows.filter(Q(archived_at__isnull=False) | Q(_inherited_archived=True))
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(employee_number__icontains=query)
            | Q(full_name__icontains=query)
            | Q(national_id__icontains=query)
            | Q(phone__icontains=query)
            | Q(address__icontains=query)
            | Q(organization_assignments__position__icontains=query)
            | Q(organization_assignments__branch__code__icontains=query)
            | Q(organization_assignments__branch__name__icontains=query)
            | Q(organization_assignments__department__code__icontains=query)
            | Q(organization_assignments__department__name__icontains=query)
        )
    if status:
        rows = rows.filter(status=status)
    if branch_id:
        rows = rows.filter(organization_assignments__branch_id=branch_id, organization_assignments__effective_to__isnull=True)
    if department_id:
        rows = rows.filter(
            organization_assignments__department_id=department_id,
            organization_assignments__effective_to__isnull=True,
        )
    return rows.distinct().order_by("employee_number", "full_name")


def serialize_branch(branch: Branch) -> dict[str, object]:
    return {
        "id": str(branch.pk),
        "code": branch.code,
        "name": branch.name,
        "location": branch.location,
        "address": branch.address,
        "manager": branch.manager_name,
        "type": branch.get_kind_display(),
        "kind": branch.kind,
        "status": "Archived" if branch.archived_at else ("Active" if branch.is_active else "Inactive"),
        "archived": branch.archived_at is not None,
        "archivedAt": branch.archived_at.isoformat() if branch.archived_at else None,
        "archivedReason": branch.archived_reason,
        "deleted": branch.deleted_at is not None,
        "deletedAt": branch.deleted_at.isoformat() if branch.deleted_at else None,
        "deletionReason": branch.deletion_reason,
        "purgeAfter": branch.purge_after.isoformat() if branch.purge_after else None,
    }


def serialize_department(department: Department) -> dict[str, object]:
    return {
        "id": str(department.pk),
        "code": department.code,
        "name": department.name,
        "notes": department.notes,
        "status": "Archived" if department.archived_at else ("Active" if department.is_active else "Inactive"),
        "archived": department.archived_at is not None,
        "archivedAt": department.archived_at.isoformat() if department.archived_at else None,
        "archivedReason": department.archived_reason,
        "deleted": department.deleted_at is not None,
        "deletedAt": department.deleted_at.isoformat() if department.deleted_at else None,
        "deletionReason": department.deletion_reason,
        "purgeAfter": department.purge_after.isoformat() if department.purge_after else None,
    }


def serialize_assignment(assignment: EmployeeOrganizationAssignment) -> dict[str, object]:
    return {
        "id": str(assignment.pk),
        "effective": assignment.effective_from.isoformat(),
        "effectiveTo": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "branchId": str(assignment.branch_id),
        "branch": assignment.branch.name,
        "departmentId": str(assignment.department_id),
        "department": assignment.department.name,
        "position": assignment.position,
        "reason": assignment.reason,
        "createdAt": assignment.created_at.isoformat(),
    }


def _history_for_employee(employee: InternalEmployee) -> list[EmployeeOrganizationAssignment]:
    history = getattr(employee, "organization_history", None)
    if history is not None:
        return list(history)
    return list(employee.organization_assignments.select_related("branch", "department").order_by("-effective_from", "-created_at"))


def serialize_employee(employee: InternalEmployee) -> dict[str, object]:
    history = _history_for_employee(employee)
    # Only an open assignment inherits current parent lifecycle. A closed historical
    # assignment must never make a terminated/transferred employee disappear merely
    # because an old branch/department is archived later. Keep the latest row only
    # for display when no assignment is currently open.
    current = next((row for row in history if row.effective_to is None), None)
    display_assignment = current or (history[0] if history else None)

    inherited_archive_sources: list[str] = []
    inherited_delete_sources: list[str] = []
    inherited_archived_at = None
    inherited_deleted_at = None
    inherited_purge_after = None
    if current is not None:
        for label, parent in (("branch", current.branch), ("department", current.department)):
            if parent.archived_at:
                inherited_archive_sources.append(label)
                if inherited_archived_at is None or parent.archived_at < inherited_archived_at:
                    inherited_archived_at = parent.archived_at
            if parent.deleted_at:
                inherited_delete_sources.append(label)
                if inherited_deleted_at is None or parent.deleted_at < inherited_deleted_at:
                    inherited_deleted_at = parent.deleted_at
                if parent.purge_after and (inherited_purge_after is None or parent.purge_after < inherited_purge_after):
                    inherited_purge_after = parent.purge_after

    effective_archived = employee.archived_at is not None or bool(inherited_archive_sources)
    effective_deleted = employee.deleted_at is not None or bool(inherited_delete_sources)
    archive_reason = employee.archived_reason
    if not archive_reason and inherited_archive_sources:
        archive_reason = "Inherited from archived " + " / ".join(inherited_archive_sources)
    deletion_reason = employee.deletion_reason
    if not deletion_reason and inherited_delete_sources:
        deletion_reason = "Inherited from deleted " + " / ".join(inherited_delete_sources)

    return {
        "id": str(employee.pk),
        "employeeId": employee.employee_number,
        "employeeNumber": employee.employee_number,
        "name": employee.full_name,
        "position": display_assignment.position if display_assignment else "",
        "department": display_assignment.department.name if display_assignment else "",
        "departmentId": str(display_assignment.department_id) if display_assignment else None,
        "branchId": str(display_assignment.branch_id) if display_assignment else None,
        "branch": display_assignment.branch.name if display_assignment else "",
        "joining": employee.joining_date.isoformat(),
        "employmentEnd": employee.employment_end_date.isoformat() if employee.employment_end_date else None,
        "status": employee.get_status_display(),
        "archived": effective_archived,
        "archivedOwn": employee.archived_at is not None,
        "archivedAt": (employee.archived_at or inherited_archived_at).isoformat() if (employee.archived_at or inherited_archived_at) else None,
        "archivedReason": archive_reason,
        "deleted": effective_deleted,
        "deletedOwn": employee.deleted_at is not None,
        "deletedAt": (employee.deleted_at or inherited_deleted_at).isoformat() if (employee.deleted_at or inherited_deleted_at) else None,
        "deletionReason": deletion_reason,
        "purgeAfter": (employee.purge_after or inherited_purge_after).isoformat() if (employee.purge_after or inherited_purge_after) else None,
        "cascadeLifecycle": {
            "archiveSources": inherited_archive_sources,
            "deleteSources": inherited_delete_sources,
        },
        "nationalId": employee.national_id,
        "phone": employee.phone,
        "address": employee.address,
        # Owned by the salary and payment domains.
        "paymentMethod": "Not set",
        "wps": "Needs setup",
        "basicSalary": None,
    }



def serialize_employee_lifecycle(employee: InternalEmployee) -> dict[str, object]:
    """Return policy-derived capabilities for one employee profile/action surface.

    This is deliberately separate from ``serialize_employee`` so register/list endpoints do not
    execute history-blocker queries per row.
    """

    return lifecycle_capabilities(employee)

def internal_master_context(*, company: Company) -> dict[str, object]:
    branches = list(branches_for_company(company=company, archived=None))
    departments = list(departments_for_company(company=company, archived=None))
    employees = list(employees_for_company(company=company))
    histories = {
        str(employee.pk): [serialize_assignment(item) for item in _history_for_employee(employee)]
        for employee in employees
    }
    return {
        "branches": [serialize_branch(item) for item in branches],
        "departments": [serialize_department(item) for item in departments],
        "employees": [serialize_employee(item) for item in employees],
        "employeeOrganizationHistory": histories,
    }
