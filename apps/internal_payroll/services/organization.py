from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit
from apps.accounts.roles import Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.lifecycle import (
    LifecycleAction,
    record_lifecycle_action,
    require_lifecycle_action,
)
from apps.core.services.numbering import allocate_number
from apps.core.trash import move_to_trash, restore_from_trash
from apps.internal_payroll.models import (
    Branch,
    BranchKind,
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
            "kind": obj.kind,
            "is_active": obj.is_active,
            "archived_at": obj.archived_at.isoformat() if obj.archived_at else None,
            "archived_reason": obj.archived_reason,
            "deleted_at": obj.deleted_at.isoformat() if obj.deleted_at else None,
            "deletion_reason": obj.deletion_reason,
            "purge_after": obj.purge_after.isoformat() if obj.purge_after else None,
        }
    if isinstance(obj, Department):
        return {
            "code": obj.code, "name": obj.name, "notes": obj.notes, "is_active": obj.is_active,
            "archived_at": obj.archived_at.isoformat() if obj.archived_at else None,
            "archived_reason": obj.archived_reason,
            "deleted_at": obj.deleted_at.isoformat() if obj.deleted_at else None,
            "deletion_reason": obj.deletion_reason,
            "purge_after": obj.purge_after.isoformat() if obj.purge_after else None,
        }
    if isinstance(obj, InternalEmployee):
        return {
            "employee_number": obj.employee_number,
            "full_name": obj.full_name,
            "national_id": obj.national_id,
            "phone": obj.phone,
            "joining_date": obj.joining_date.isoformat(),
            "employment_end_date": obj.employment_end_date.isoformat() if obj.employment_end_date else None,
            "status": obj.status,
            "archived_at": obj.archived_at.isoformat() if obj.archived_at else None,
            "archived_reason": obj.archived_reason,
            "deleted_at": obj.deleted_at.isoformat() if obj.deleted_at else None,
            "deletion_reason": obj.deletion_reason,
            "purge_after": obj.purge_after.isoformat() if obj.purge_after else None,
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
    if branch.deleted_at:
        raise ValidationError({"branch": "Choose a current branch or office; this record is in Trash."})
    if branch.archived_at:
        raise ValidationError({"branch": "Choose a current branch or office; this record is archived."})
    if not branch.is_active:
        raise ValidationError({"branch": "Choose an active branch or office."})
    if department.deleted_at:
        raise ValidationError({"department": "Choose a current department; this record is in Trash."})
    if department.archived_at:
        raise ValidationError({"department": "Choose a current department; this record is archived."})
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
    kind: str = BranchKind.BRANCH,
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
        kind=(kind or BranchKind.BRANCH).strip().lower(),
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
    kind: str = BranchKind.BRANCH,
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> Branch:
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company)
    before = _model_snapshot(branch)
    next_active = _active_flag(is_active)
    lifecycle_decision = None
    if branch.archived_at and next_active:
        raise ValidationError({"status": "Restore the archived branch or office before making it active."})
    if branch.is_active and not next_active:
        lifecycle_decision = require_lifecycle_action(branch, LifecycleAction.DEACTIVATE)
    branch.code = code
    branch.name = name
    branch.location = location
    branch.address = address
    branch.manager_name = manager_name
    branch.kind = (kind or branch.kind).strip().lower()
    branch.is_active = next_active
    branch.full_clean()
    try:
        branch.save()
    except IntegrityError as exc:
        raise ValidationError("Branch code and name must be unique within the company.") from exc
    after = _model_snapshot(branch)
    if before != after:
        if lifecycle_decision is not None:
            record_lifecycle_action(
                instance=branch, decision=lifecycle_decision, actor_membership=actor_membership,
                before=before, after=after, audit_action="internal.branch.deactivated", request=request,
            )
        else:
            record_audit_event(
                company=branch.company, area=AuditArea.INTERNAL, action="internal.branch.updated",
                object_type="internal_payroll.Branch", object_id=branch.pk, object_label=str(branch),
                actor_membership=actor_membership, before=before, after=after, request=request,
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
    lifecycle_decision = None
    if department.archived_at and next_active:
        raise ValidationError({"status": "Restore the archived department before making it active."})
    if department.is_active and not next_active:
        lifecycle_decision = require_lifecycle_action(department, LifecycleAction.DEACTIVATE)
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
        if lifecycle_decision is not None:
            record_lifecycle_action(
                instance=department, decision=lifecycle_decision, actor_membership=actor_membership,
                before=before, after=after, audit_action="internal.department.deactivated", request=request,
            )
        else:
            record_audit_event(
                company=department.company, area=AuditArea.INTERNAL, action="internal.department.updated",
                object_type="internal_payroll.Department", object_id=department.pk, object_label=str(department),
                actor_membership=actor_membership, before=before, after=after, request=request,
            )
    return department


@transaction.atomic
def archive_branch(*, actor_membership: CompanyMembership, branch_id, reason: str, request: HttpRequest | None = None) -> Branch:
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company)
    if branch.archived_at:
        return branch
    decision = require_lifecycle_action(branch, LifecycleAction.ARCHIVE, reason=reason)
    before = _model_snapshot(branch)
    # Keep the branch's own Active/Inactive state intact. Archive is an
    # independent reversible lifecycle boundary; current employees inherit it
    # operationally through their current organization assignment.
    branch.archived_at = timezone.now()
    branch.archived_reason = (reason or "").strip()
    branch.full_clean()
    branch.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=branch, decision=decision, actor_membership=actor_membership, before=before,
        after=_model_snapshot(branch), reason=reason, audit_action="internal.branch.archived",
        metadata={"cascade_scope": "current_employees", "affected_employees": decision.evidence.get("current_employees", 0)},
        request=request,
    )
    return branch


@transaction.atomic
def restore_branch_archive(*, actor_membership: CompanyMembership, branch_id, reason: str = "", request: HttpRequest | None = None) -> Branch:
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company)
    if not branch.archived_at:
        return branch
    decision = require_lifecycle_action(branch, LifecycleAction.RESTORE)
    before = _model_snapshot(branch)
    previous_reason = branch.archived_reason
    branch.archived_at = None
    branch.archived_reason = ""
    branch.full_clean()
    branch.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=branch, decision=decision, actor_membership=actor_membership, before=before,
        after=_model_snapshot(branch), reason=reason, audit_action="internal.branch.archive_restored",
        metadata={"previous_archive_reason": previous_reason, "restored_active_state": branch.is_active, "cascade_scope": "current_employees"},
        request=request,
    )
    return branch


@transaction.atomic
def delete_unused_branch(*, actor_membership: CompanyMembership, branch_id, confirmation: str, reason: str = "", request: HttpRequest | None = None) -> str:
    """Soft-delete a branch/office for 30 days; current employees inherit the boundary."""
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company, deleted_at__isnull=True)
    decision = require_lifecycle_action(branch, LifecycleAction.DELETE, confirmation=confirmation, reason=reason)
    before = _model_snapshot(branch)
    move_to_trash(branch, user=actor_membership.user, reason=reason)
    record_lifecycle_action(
        instance=branch, decision=decision, actor_membership=actor_membership, before=before, after=_model_snapshot(branch),
        reason=reason, audit_action="internal.branch.moved_to_trash",
        metadata={"retention_days": 30, "cascade_scope": "current_employees", "affected_employees": decision.evidence.get("current_employees", 0)},
        request=request,
    )
    return str(branch.pk)


@transaction.atomic
def restore_branch_trash(*, actor_membership: CompanyMembership, branch_id, request: HttpRequest | None = None) -> Branch:
    _require_internal_edit(actor_membership)
    branch = Branch.objects.select_for_update().get(pk=branch_id, company=actor_membership.company, deleted_at__isnull=False)
    before = _model_snapshot(branch)
    if not restore_from_trash(branch):
        raise ValidationError({"record": "This Trash item has expired and can no longer be restored."})
    record_audit_event(company=branch.company, area=AuditArea.INTERNAL, action="internal.branch.trash_restored", object_type="internal_payroll.Branch", object_id=branch.pk, object_label=str(branch), actor_membership=actor_membership, before=before, after=_model_snapshot(branch), request=request)
    return branch


@transaction.atomic
def archive_department(*, actor_membership: CompanyMembership, department_id, reason: str, request: HttpRequest | None = None) -> Department:
    _require_internal_edit(actor_membership)
    department = Department.objects.select_for_update().get(pk=department_id, company=actor_membership.company)
    if department.archived_at:
        return department
    decision = require_lifecycle_action(department, LifecycleAction.ARCHIVE, reason=reason)
    before = _model_snapshot(department)
    # Preserve the department's own Active/Inactive state; current employees
    # inherit the archive state from their open organization assignment.
    department.archived_at = timezone.now()
    department.archived_reason = (reason or "").strip()
    department.full_clean()
    department.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=department, decision=decision, actor_membership=actor_membership, before=before,
        after=_model_snapshot(department), reason=reason, audit_action="internal.department.archived",
        metadata={"cascade_scope": "current_employees", "affected_employees": decision.evidence.get("current_employees", 0)},
        request=request,
    )
    return department


@transaction.atomic
def restore_department_archive(*, actor_membership: CompanyMembership, department_id, reason: str = "", request: HttpRequest | None = None) -> Department:
    _require_internal_edit(actor_membership)
    department = Department.objects.select_for_update().get(pk=department_id, company=actor_membership.company)
    if not department.archived_at:
        return department
    decision = require_lifecycle_action(department, LifecycleAction.RESTORE)
    before = _model_snapshot(department); previous_reason = department.archived_reason
    department.archived_at = None
    department.archived_reason = ""
    department.full_clean()
    department.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=department, decision=decision, actor_membership=actor_membership, before=before,
        after=_model_snapshot(department), reason=reason, audit_action="internal.department.archive_restored",
        metadata={"previous_archive_reason": previous_reason, "restored_active_state": department.is_active, "cascade_scope": "current_employees"},
        request=request,
    )
    return department


@transaction.atomic
def delete_unused_department(*, actor_membership: CompanyMembership, department_id, confirmation: str, reason: str = "", request: HttpRequest | None = None) -> str:
    """Move a department to the 30-day Trash while retaining all historical references."""
    _require_internal_edit(actor_membership)
    department = Department.objects.select_for_update().get(pk=department_id, company=actor_membership.company, deleted_at__isnull=True)
    decision = require_lifecycle_action(department, LifecycleAction.DELETE, confirmation=confirmation, reason=reason)
    before = _model_snapshot(department)
    move_to_trash(department, user=actor_membership.user, reason=reason)
    record_lifecycle_action(
        instance=department, decision=decision, actor_membership=actor_membership, before=before,
        after=_model_snapshot(department), reason=reason, audit_action="internal.department.moved_to_trash",
        metadata={"retention_days": 30, "cascade_scope": "current_employees", "affected_employees": decision.evidence.get("current_employees", 0)},
        request=request,
    )
    return str(department.pk)


@transaction.atomic
def restore_department_trash(*, actor_membership: CompanyMembership, department_id, request: HttpRequest | None = None) -> Department:
    _require_internal_edit(actor_membership)
    department = Department.objects.select_for_update().get(pk=department_id, company=actor_membership.company, deleted_at__isnull=False)
    before = _model_snapshot(department)
    if not restore_from_trash(department):
        raise ValidationError({"record": "This Trash item has expired and can no longer be restored."})
    record_audit_event(company=department.company, area=AuditArea.INTERNAL, action="internal.department.trash_restored", object_type="internal_payroll.Department", object_id=department.pk, object_label=str(department), actor_membership=actor_membership, before=before, after=_model_snapshot(department), request=request)
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
        effective_to=employee.employment_end_date if employee.status == EmploymentStatus.TERMINATED else None,
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
    if employee.archived_at:
        raise ValidationError({"employee": "Restore the archived employee before changing organization."})
    if employee.status == EmploymentStatus.TERMINATED:
        raise ValidationError({"employee": "Terminated employment cannot be reassigned. Create a deliberate rehire/onboarding record instead."})
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


@transaction.atomic
def change_employee_lifecycle(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    action: str,
    effective_date=None,
    reason: str = "",
    request: HttpRequest | None = None,
) -> InternalEmployee:
    """Apply an explicit employment lifecycle transition without rewriting payroll history.

    Active/on-leave/inactive are current operational states. Termination is effective-dated
    through ``employment_end_date`` and closes the open organization assignment at the same
    date. A terminated employee is not silently reactivated; rehire should be a deliberate
    onboarding decision instead of rewriting the old employment period.
    """

    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company)
    if employee.archived_at:
        raise ValidationError({"employee": "Restore the archived employee before changing employment status."})

    normalized = (action or "").strip().lower().replace("-", "_").replace(" ", "_")
    transitions = {
        "activate": EmploymentStatus.ACTIVE,
        "return_active": EmploymentStatus.ACTIVE,
        "leave": EmploymentStatus.ON_LEAVE,
        "on_leave": EmploymentStatus.ON_LEAVE,
        "deactivate": EmploymentStatus.INACTIVE,
        "inactive": EmploymentStatus.INACTIVE,
        "stop_activity": EmploymentStatus.INACTIVE,
        "terminate": EmploymentStatus.TERMINATED,
        "terminated": EmploymentStatus.TERMINATED,
    }
    if normalized not in transitions:
        raise ValidationError({"action": "Unknown employee lifecycle action."})

    target = transitions[normalized]
    lifecycle_decision = None
    if target == EmploymentStatus.INACTIVE:
        lifecycle_decision = require_lifecycle_action(
            employee, LifecycleAction.DEACTIVATE, reason=reason
        )
    if employee.status == EmploymentStatus.TERMINATED and target != EmploymentStatus.TERMINATED:
        raise ValidationError({"action": "A terminated employment record cannot be reactivated. Create a rehire/onboarding record instead."})
    if target == EmploymentStatus.ACTIVE and employee.status not in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE, EmploymentStatus.INACTIVE}:
        raise ValidationError({"action": "This employee cannot be returned to Active from the current status."})
    if target in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE}:
        current_assignment = employee.organization_assignments.select_related("branch", "department").filter(effective_to__isnull=True).first()
        if current_assignment and (current_assignment.branch.archived_at or not current_assignment.branch.is_active):
            raise ValidationError({"branch": "Move the employee to an active, current branch or office before returning employment to an eligible status."})
        if current_assignment and (current_assignment.department.archived_at or not current_assignment.department.is_active):
            raise ValidationError({"department": "Move the employee to an active, current department before returning employment to an eligible status."})
    if target == EmploymentStatus.ON_LEAVE and employee.status not in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE}:
        raise ValidationError({"action": "Only an active employee can be placed on leave."})

    reason = (reason or "").strip()
    if target in {EmploymentStatus.ON_LEAVE, EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED} and not reason:
        raise ValidationError({"reason": "A reason is required for leave, deactivation, or termination."})

    before = _model_snapshot(employee)
    metadata = {"reason": reason, "from_status": employee.status, "to_status": target}

    if target == EmploymentStatus.TERMINATED:
        if effective_date is None:
            raise ValidationError({"effective_date": "Employment end date is required when terminating an employee."})
        if effective_date < employee.joining_date:
            raise ValidationError({"effective_date": "Employment end date cannot be before the joining date."})
        if effective_date > timezone.localdate():
            raise ValidationError({"effective_date": "Future-dated termination is not supported by this workflow."})
        open_assignment = (
            EmployeeOrganizationAssignment.objects.select_for_update()
            .filter(company=employee.company, employee=employee, effective_to__isnull=True)
            .order_by("-effective_from", "-created_at")
            .first()
        )
        if open_assignment:
            if effective_date < open_assignment.effective_from:
                raise ValidationError({"effective_date": "Employment cannot end before the current organization assignment starts."})
            open_assignment.effective_to = effective_date
            open_assignment.full_clean()
            open_assignment.save(update_fields=["effective_to", "updated_at"])
        employee.employment_end_date = effective_date
        metadata["effective_date"] = effective_date.isoformat()
    elif target != EmploymentStatus.TERMINATED:
        # Non-terminal operational state changes do not invent an employment end date.
        employee.employment_end_date = None

    employee.status = target
    employee.full_clean()
    employee.save(update_fields=["status", "employment_end_date", "updated_at"])
    after = _model_snapshot(employee)
    if lifecycle_decision is not None:
        record_lifecycle_action(
            instance=employee,
            decision=lifecycle_decision,
            actor_membership=actor_membership,
            before=before,
            after=after,
            reason=reason,
            audit_action=f"internal.employee.lifecycle.{target}",
            metadata={"from_status": before["status"], "to_status": target},
            request=request,
        )
    else:
        record_audit_event(
            company=employee.company,
            area=AuditArea.INTERNAL,
            action=f"internal.employee.lifecycle.{target}",
            object_type="internal_payroll.InternalEmployee",
            object_id=employee.pk,
            object_label=str(employee),
            actor_membership=actor_membership,
            before=before,
            after=after,
            metadata=metadata,
            request=request,
        )
    return employee


@transaction.atomic
def archive_employee(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    reason: str,
    request: HttpRequest | None = None,
) -> InternalEmployee:
    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company)
    if employee.archived_at:
        return employee
    reason = (reason or "").strip()
    lifecycle_decision = require_lifecycle_action(
        employee, LifecycleAction.ARCHIVE, reason=reason
    )
    before = _model_snapshot(employee)
    employee.archived_at = timezone.now()
    employee.archived_reason = reason
    employee.full_clean()
    employee.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=employee, decision=lifecycle_decision, actor_membership=actor_membership,
        before=before, after=_model_snapshot(employee), reason=reason,
        audit_action="internal.employee.archived", request=request,
    )
    return employee


@transaction.atomic
def restore_employee_archive(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    reason: str = "",
    request: HttpRequest | None = None,
) -> InternalEmployee:
    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company)
    if not employee.archived_at:
        return employee
    lifecycle_decision = require_lifecycle_action(employee, LifecycleAction.RESTORE)
    before = _model_snapshot(employee)
    prior_reason = employee.archived_reason
    employee.archived_at = None
    employee.archived_reason = ""
    employee.full_clean()
    employee.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(
        instance=employee, decision=lifecycle_decision, actor_membership=actor_membership,
        before=before, after=_model_snapshot(employee), reason=(reason or "").strip(),
        audit_action="internal.employee.archive_restored",
        metadata={"previous_archive_reason": prior_reason}, request=request,
    )
    return employee



@transaction.atomic
def delete_unused_employee(
    *, actor_membership: CompanyMembership, employee_id, confirmation: str, reason: str = "", request: HttpRequest | None = None,
) -> str:
    """Move an employee master into 30-day recoverable Delete; never erase payroll history."""
    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company, deleted_at__isnull=True)
    decision = require_lifecycle_action(employee, LifecycleAction.DELETE, confirmation=confirmation, reason=reason)
    before = _model_snapshot(employee)
    move_to_trash(employee, user=actor_membership.user, reason=reason)
    record_lifecycle_action(instance=employee, decision=decision, actor_membership=actor_membership, before=before, after=_model_snapshot(employee), reason=reason, audit_action="internal.employee.moved_to_trash", metadata={"retention_days":30}, request=request)
    return str(employee.pk)


@transaction.atomic
def restore_employee_trash(*, actor_membership: CompanyMembership, employee_id, request: HttpRequest | None = None) -> InternalEmployee:
    _require_internal_edit(actor_membership)
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=actor_membership.company, deleted_at__isnull=False)
    before = _model_snapshot(employee)
    if not restore_from_trash(employee):
        raise ValidationError({"employee": "This Trash item has expired and can no longer be restored."})
    record_audit_event(company=employee.company, area=AuditArea.INTERNAL, action="internal.employee.trash_restored", object_type="internal_payroll.InternalEmployee", object_id=employee.pk, object_label=str(employee), actor_membership=actor_membership, before=before, after=_model_snapshot(employee), request=request)
    return employee

