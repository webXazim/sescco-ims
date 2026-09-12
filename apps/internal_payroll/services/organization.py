from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit
from apps.accounts.roles import Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number
from apps.internal_payroll.models import (
    Branch,
    Department,
    EmployeeOrganizationAssignment,
    EmploymentStatus,
    InternalEmployee,
)

EMPLOYED_STATUSES = (EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE)


def _require_internal_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot modify internal payroll master data.")


def _normalize_status(status: str) -> str:
    normalized = status.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "active": EmploymentStatus.ACTIVE,
        "on_leave": EmploymentStatus.ON_LEAVE,
        "inactive": EmploymentStatus.INACTIVE,
        "terminated": EmploymentStatus.TERMINATED,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError({"status": "Unknown employee status."}) from exc


def _active_flag(status: str | bool) -> bool:
    if isinstance(status, bool):
        return status
    normalized = status.strip().lower()
    if normalized in {"active", "true", "1"}:
        return True
    if normalized in {"inactive", "false", "0"}:
        return False
    raise ValidationError({"status": "Status must be Active or Inactive."})


def _model_snapshot(obj) -> dict[str, object]:
    if isinstance(obj, Branch):
        return {
            "code": obj.code,
            "name": obj.name,
            "location": obj.location,
            "address": obj.address,
            "manager_name": obj.manager_name,
            "is_active": obj.is_active,
        }
    if isinstance(obj, Department):
        return {"code": obj.code, "name": obj.name, "notes": obj.notes, "is_active": obj.is_active}
    if isinstance(obj, InternalEmployee):
        return {
            "employee_number": obj.employee_number,
            "full_name": obj.full_name,
            "national_id": obj.national_id,
            "phone": obj.phone,
            "joining_date": obj.joining_date.isoformat(),
            "employment_end_date": obj.employment_end_date.isoformat() if obj.employment_end_date else None,
            "status": obj.status,
        }
    if isinstance(obj, EmployeeOrganizationAssignment):
        return {
            "employee_id": str(obj.employee_id),
            "branch_id": str(obj.branch_id),
            "department_id": str(obj.department_id),
            "position": obj.position,
            "effective_from": obj.effective_from.isoformat(),
            "effective_to": obj.effective_to.isoformat() if obj.effective_to else None,
            "reason": obj.reason,
        }
    raise TypeError(f"Unsupported snapshot type: {type(obj)!r}")


def _validate_company_master(*, membership: CompanyMembership, branch: Branch, department: Department) -> None:
    company_id = membership.company_id
    if branch.company_id != company_id:
        raise ValidationError({"branch": "Branch does not belong to the active company."})
    if department.company_id != company_id:
        raise ValidationError({"department": "Department does not belong to the active company."})
    if not branch.is_active:
        raise ValidationError({"branch": "Choose an active branch or office."})
    if not department.is_active:
        raise ValidationError({"department": "Choose an active department."})


@transaction.atomic
def create_branch(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    location: str = "",
    address: str = "",
    manager_name: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> Branch:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    code = code.strip() or allocate_number(company=company, key="internal.branch", prefix="BR-", padding=4)
    branch = Branch(
        company=company,
        code=code,
        name=name,
        location=location,
        address=address,
        manager_name=manager_name,
        is_active=_active_flag(is_active),
    )
    branch.full_clean()
    try:
        branch.save()
    except IntegrityError as exc:
        raise ValidationError("Branch code and name must be unique within the company.") from exc
    record_audit_event(
        company=branch.company,
        area=AuditArea.INTERNAL,
        action="internal.branch.created",
        object_type="internal_payroll.Branch",
        object_id=branch.pk,
        object_label=str(branch),
        actor_membership=actor_membership,
        after=_model_snapshot(branch),
        request=request,
    )
    return branch


@transaction.atomic
def update_branch(
    *,
    actor_membership: CompanyMembership,
    branch_id,
    code: str,
    name: str,
    location: str = "",
    address: str = "",
    manager_name: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> Branch:
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company)
    before = _model_snapshot(branch)
    next_active = _active_flag(is_active)
    if branch.is_active and not next_active:
        has_employees = InternalEmployee.objects.for_company(branch.company).filter(
            status__in=EMPLOYED_STATUSES,
            organization_assignments__branch=branch,
            organization_assignments__effective_to__isnull=True,
        ).exists()
        if has_employees:
            raise ValidationError("Transfer or deactivate current employees before making this branch inactive.")
    branch.code = code
    branch.name = name
    branch.location = location
    branch.address = address
    branch.manager_name = manager_name
    branch.is_active = next_active
    branch.full_clean()
    try:
        branch.save()
    except IntegrityError as exc:
        raise ValidationError("Branch code and name must be unique within the company.") from exc
    after = _model_snapshot(branch)
    if before != after:
        record_audit_event(
            company=branch.company,
            area=AuditArea.INTERNAL,
            action="internal.branch.updated",
            object_type="internal_payroll.Branch",
            object_id=branch.pk,
            object_label=str(branch),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return branch


@transaction.atomic
def create_department(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> Department:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    code = code.strip() or allocate_number(company=company, key="internal.department", prefix="DEP-", padding=4)
    department = Department(
        company=company,
        code=code,
        name=name,
        notes=notes,
        is_active=_active_flag(is_active),
    )
    department.full_clean()
    try:
        department.save()
    except IntegrityError as exc:
        raise ValidationError("Department code and name must be unique within the company.") from exc
    record_audit_event(
        company=department.company,
        area=AuditArea.INTERNAL,
        action="internal.department.created",
        object_type="internal_payroll.Department",
        object_id=department.pk,
        object_label=str(department),
        actor_membership=actor_membership,
        after=_model_snapshot(department),
        request=request,
    )
    return department


@transaction.atomic
def update_department(
    *,
    actor_membership: CompanyMembership,
    department_id,
    code: str,
    name: str,
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> Department:
    _require_internal_edit(actor_membership)
    department = Department.objects.select_for_update().get(pk=department_id, company=actor_membership.company)
    before = _model_snapshot(department)
    next_active = _active_flag(is_active)
    if department.is_active and not next_active:
        has_employees = InternalEmployee.objects.for_company(department.company).filter(
            status__in=EMPLOYED_STATUSES,
            organization_assignments__department=department,
            organization_assignments__effective_to__isnull=True,
        ).exists()
        if has_employees:
            raise ValidationError("Move or deactivate current employees before making this department inactive.")
    department.code = code
    department.name = name
    department.notes = notes
    department.is_active = next_active
    department.full_clean()
    try:
        department.save()
    except IntegrityError as exc:
        raise ValidationError("Department code and name must be unique within the company.") from exc
    after = _model_snapshot(department)
    if before != after:
        record_audit_event(
            company=department.company,
            area=AuditArea.INTERNAL,
            action="internal.department.updated",
            object_type="internal_payroll.Department",
            object_id=department.pk,
            object_label=str(department),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return department


@transaction.atomic
def create_employee(
    *,
    actor_membership: CompanyMembership,
    employee_number: str,
    full_name: str,
    joining_date,
    branch_id,
    department_id,
    position: str,
    status: str = EmploymentStatus.ACTIVE,
    national_id: str = "",
    phone: str = "",
    address: str = "",
    employment_end_date=None,
    reason: str = "Employee onboarding",
    request: HttpRequest | None = None,
) -> InternalEmployee:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    employee_number = employee_number.strip() or allocate_number(company=company, key="internal.employee", prefix="", padding=4)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=company)
    department = Department.objects.select_for_update().get(pk=department_id, company=company)
    _validate_company_master(membership=actor_membership, branch=branch, department=department)
    employee = InternalEmployee(
        company=company,
        employee_number=employee_number,
        full_name=full_name,
        national_id=national_id,
        phone=phone,
        address=address,
        joining_date=joining_date,
        employment_end_date=employment_end_date,
        status=_normalize_status(status),
    )
    employee.full_clean()
    try:
        employee.save()
    except IntegrityError as exc:
        raise ValidationError("Employee number and non-empty national ID must be unique within the company.") from exc
    assignment = EmployeeOrganizationAssignment(
        company=company,
        employee=employee,
        branch=branch,
        department=department,
        position=position,
        effective_from=employee.joining_date,
        reason=reason,
    )
    assignment.full_clean()
    assignment.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.employee.created",
        object_type="internal_payroll.InternalEmployee",
        object_id=employee.pk,
        object_label=str(employee),
        actor_membership=actor_membership,
        after={**_model_snapshot(employee), "organization": _model_snapshot(assignment)},
        request=request,
    )
    return employee


@transaction.atomic
def update_employee(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    employee_number: str,
    full_name: str,
    joining_date,
    status: str,
    national_id: str = "",
    phone: str = "",
    address: str = "",
    employment_end_date=None,
    request: HttpRequest | None = None,
) -> InternalEmployee:
    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company)
    before = _model_snapshot(employee)
    first_assignment = employee.organization_assignments.order_by("effective_from", "created_at").first()
    if first_assignment and joining_date > first_assignment.effective_from:
        raise ValidationError({"joining_date": "Joining date cannot be later than the first organization assignment."})
    employee.employee_number = employee_number
    employee.full_name = full_name
    employee.national_id = national_id
    employee.phone = phone
    employee.address = address
    employee.joining_date = joining_date
    employee.employment_end_date = employment_end_date
    employee.status = _normalize_status(status)
    employee.full_clean()
    try:
        employee.save()
    except IntegrityError as exc:
        raise ValidationError("Employee number and non-empty national ID must be unique within the company.") from exc
    after = _model_snapshot(employee)
    if before != after:
        record_audit_event(
            company=employee.company,
            area=AuditArea.INTERNAL,
            action="internal.employee.updated",
            object_type="internal_payroll.InternalEmployee",
            object_id=employee.pk,
            object_label=str(employee),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return employee


@transaction.atomic
def change_employee_organization(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    branch_id,
    department_id,
    position: str,
    effective_from,
    reason: str = "Organization change",
    request: HttpRequest | None = None,
) -> EmployeeOrganizationAssignment:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=company)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=company)
    department = Department.objects.select_for_update().get(pk=department_id, company=company)
    _validate_company_master(membership=actor_membership, branch=branch, department=department)
    if effective_from < employee.joining_date:
        raise ValidationError({"effective_from": "Organization change cannot be before the employee joining date."})
    if effective_from > timezone.localdate():
        raise ValidationError({"effective_from": "Future-dated organization changes are not supported by this workflow."})

    assignments = list(
        EmployeeOrganizationAssignment.objects.select_for_update()
        .filter(company=company, employee=employee)
        .order_by("effective_from", "created_at")
    )
    if not assignments:
        raise ValidationError("Employee has no initial organization assignment.")
    if any(item.effective_from > effective_from for item in assignments):
        raise ValidationError({"effective_from": "This date is earlier than an existing later organization assignment."})

    current = assignments[-1]
    if effective_from < current.effective_from:
        raise ValidationError({"effective_from": "Choose a date on or after the latest organization assignment."})
    if (
        current.branch_id == branch.pk
        and current.department_id == department.pk
        and current.position.strip() == position.strip()
    ):
        raise ValidationError("No organization change was detected.")

    before = _model_snapshot(current)
    if effective_from == current.effective_from:
        current.branch = branch
        current.department = department
        current.position = position
        current.reason = reason
        current.full_clean()
        current.save()
        next_assignment = current
    else:
        current.effective_to = effective_from - timedelta(days=1)
        current.full_clean()
        current.save(update_fields=("effective_to", "updated_at"))
        next_assignment = EmployeeOrganizationAssignment(
            company=company,
            employee=employee,
            branch=branch,
            department=department,
            position=position,
            effective_from=effective_from,
            reason=reason,
        )
        next_assignment.full_clean()
        next_assignment.save()

    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.employee.organization_changed",
        object_type="internal_payroll.InternalEmployee",
        object_id=employee.pk,
        object_label=str(employee),
        actor_membership=actor_membership,
        before={"organization": before},
        after={"organization": _model_snapshot(next_assignment)},
        request=request,
    )
    return next_assignment
