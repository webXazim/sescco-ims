from __future__ import annotations

from django.db.models import Prefetch, Q, QuerySet

from apps.core.models import Company
from apps.internal_payroll.models import Branch, Department, EmployeeOrganizationAssignment, InternalEmployee


def branches_for_company(*, company: Company, query: str = "", active: bool | None = None) -> QuerySet[Branch]:
    rows = Branch.objects.for_company(company)
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


def departments_for_company(*, company: Company, query: str = "", active: bool | None = None) -> QuerySet[Department]:
    rows = Department.objects.for_company(company)
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
) -> QuerySet[InternalEmployee]:
    assignment_history = EmployeeOrganizationAssignment.objects.for_company(company).select_related(
        "branch", "department"
    ).order_by("-effective_from", "-created_at")
    rows = InternalEmployee.objects.for_company(company).prefetch_related(
        Prefetch("organization_assignments", queryset=assignment_history, to_attr="organization_history")
    )
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(employee_number__icontains=query)
            | Q(full_name__icontains=query)
            | Q(national_id__icontains=query)
            | Q(phone__icontains=query)
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
        "status": "Active" if branch.is_active else "Inactive",
    }


def serialize_department(department: Department) -> dict[str, object]:
    return {
        "id": str(department.pk),
        "code": department.code,
        "name": department.name,
        "notes": department.notes,
        "status": "Active" if department.is_active else "Inactive",
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
    current = history[0] if history else None
    return {
        "id": str(employee.pk),
        "employeeId": employee.employee_number,
        "employeeNumber": employee.employee_number,
        "name": employee.full_name,
        "position": current.position if current else "",
        "department": current.department.name if current else "",
        "departmentId": str(current.department_id) if current else None,
        "branchId": str(current.branch_id) if current else None,
        "branch": current.branch.name if current else "",
        "joining": employee.joining_date.isoformat(),
        "employmentEnd": employee.employment_end_date.isoformat() if employee.employment_end_date else None,
        "status": employee.get_status_display(),
        "nationalId": employee.national_id,
        "phone": employee.phone,
        # Owned by the salary and payment domains.
        "paymentMethod": "Not set",
        "wps": "Needs setup",
        "basicSalary": None,
    }


def internal_master_context(*, company: Company) -> dict[str, object]:
    branches = list(branches_for_company(company=company))
    departments = list(departments_for_company(company=company))
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
