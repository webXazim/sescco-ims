from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable

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
from apps.core.services.numbering import allocate_number
from apps.core.services.lifecycle import LifecycleAction, record_lifecycle_action, require_lifecycle_action
from apps.internal_payroll.models import (
    InternalEmployee,
    OvertimePolicy,
    SalaryComponent,
    SalaryComponentCalculation,
    SalaryComponentCategory,
    SalaryComponentRecurrence,
    SalaryStructure,
    SalaryStructureLine,
    WPSMapping,
)


def _require_internal_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot modify internal payroll salary setup.")


def _active_flag(status: str | bool) -> bool:
    if isinstance(status, bool):
        return status
    normalized = status.strip().lower()
    if normalized in {"active", "true", "1"}:
        return True
    if normalized in {"inactive", "false", "0"}:
        return False
    raise ValidationError({"status": "Status must be Active or Inactive."})


def _enum_value(value: str, choices: type, field: str) -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    for item in choices:
        if normalized in {item.value.lower(), item.label.lower().replace(" ", "_").replace("-", "_")}:
            return item.value
    raise ValidationError({field: f"Unknown {field.replace('_', ' ')}."})


def _money(value: object, field: str = "amount") -> Decimal:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise InvalidOperation
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite monetary amount."}) from exc


def _rate(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result.quantize(Decimal("0.0001"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite number."}) from exc


def _component_snapshot(component: SalaryComponent) -> dict[str, object]:
    return {
        "code": component.code,
        "name": component.name,
        "category": component.category,
        "recurrence": component.recurrence,
        "calculation": component.calculation,
        "wps_mapping": component.wps_mapping,
        "notes": component.notes,
        "is_active": component.is_active,
        "archived_at": component.archived_at.isoformat() if component.archived_at else None,
        "archived_reason": component.archived_reason,
    }


def _policy_snapshot(policy: OvertimePolicy) -> dict[str, object]:
    return {
        "code": policy.code,
        "name": policy.name,
        "base_component_id": str(policy.base_component_id),
        "base_component_code": policy.base_component.code,
        "base_component_name": policy.base_component.name,
        "divisor": str(policy.divisor),
        "multiplier": str(policy.multiplier),
        "notes": policy.notes,
        "is_active": policy.is_active,
        "archived_at": policy.archived_at.isoformat() if policy.archived_at else None,
        "archived_reason": policy.archived_reason,
    }


def _structure_snapshot(structure: SalaryStructure, lines: Iterable[SalaryStructureLine]) -> dict[str, object]:
    return {
        "employee_id": str(structure.employee_id),
        "effective_from": structure.effective_from.isoformat(),
        "effective_to": structure.effective_to.isoformat() if structure.effective_to else None,
        "overtime_policy_id": str(structure.overtime_policy_id) if structure.overtime_policy_id else None,
        "overtime_policy_code": structure.overtime_policy_code,
        "overtime_policy_name": structure.overtime_policy_name,
        "overtime_base_component_code": structure.overtime_base_component_code,
        "overtime_base_component_name": structure.overtime_base_component_name,
        "overtime_divisor": str(structure.overtime_divisor) if structure.overtime_divisor is not None else None,
        "overtime_multiplier": str(structure.overtime_multiplier) if structure.overtime_multiplier is not None else None,
        "notes": structure.notes,
        "components": [
            {
                "component_id": str(line.component_id),
                "code": line.component_code,
                "name": line.component_name,
                "category": line.component_category,
                "recurrence": line.component_recurrence,
                "calculation": line.component_calculation,
                "wps_mapping": line.wps_mapping,
                "amount": str(line.amount),
            }
            for line in lines
        ],
    }


@transaction.atomic
def create_salary_component(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    category: str,
    recurrence: str,
    calculation: str,
    wps_mapping: str = "Not mapped",
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> SalaryComponent:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    code = code.strip() or allocate_number(company=company, key="internal.salary_component", prefix="SC-", padding=4)
    component = SalaryComponent(
        company=company,
        code=code,
        name=name,
        category=_enum_value(category, SalaryComponentCategory, "category"),
        recurrence=_enum_value(recurrence, SalaryComponentRecurrence, "recurrence"),
        calculation=_enum_value(calculation, SalaryComponentCalculation, "calculation"),
        wps_mapping=_enum_value(wps_mapping, WPSMapping, "wps_mapping"),
        notes=notes,
        is_active=_active_flag(is_active),
    )
    component.full_clean()
    try:
        component.save()
    except IntegrityError as exc:
        raise ValidationError("Salary component code/name must be unique, and only one active Basic Salary mapping is allowed.") from exc
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_component.created",
        object_type="internal_payroll.SalaryComponent",
        object_id=component.pk,
        object_label=str(component),
        actor_membership=actor_membership,
        after=_component_snapshot(component),
        request=request,
    )
    return component


@transaction.atomic
def update_salary_component(
    *,
    actor_membership: CompanyMembership,
    component_id,
    code: str,
    name: str,
    category: str,
    recurrence: str,
    calculation: str,
    wps_mapping: str,
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> SalaryComponent:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    component = SalaryComponent.objects.select_for_update().get(pk=component_id, company=company)
    if component.archived_at:
        raise ValidationError({"component": "Restore the archived salary component before editing it."})
    before = _component_snapshot(component)
    component.code = code
    component.name = name
    component.category = _enum_value(category, SalaryComponentCategory, "category")
    component.recurrence = _enum_value(recurrence, SalaryComponentRecurrence, "recurrence")
    component.calculation = _enum_value(calculation, SalaryComponentCalculation, "calculation")
    component.wps_mapping = _enum_value(wps_mapping, WPSMapping, "wps_mapping")
    component.notes = notes
    component.is_active = _active_flag(is_active)

    active_policy_uses_component = OvertimePolicy.objects.for_company(company).filter(
        base_component=component,
        is_active=True,
    ).exists()
    if active_policy_uses_component and not component.is_active:
        raise ValidationError({
            "status": "Deactivate or change the active overtime policy before deactivating its base salary component."
        })
    if active_policy_uses_component and (
        component.category != SalaryComponentCategory.EARNING
        or component.recurrence != SalaryComponentRecurrence.RECURRING
    ):
        raise ValidationError({
            "category": "A component used by an active overtime policy must remain a recurring earning component."
        })

    component.full_clean()
    try:
        component.save()
    except IntegrityError as exc:
        raise ValidationError("Salary component code/name must be unique, and only one active Basic Salary mapping is allowed.") from exc
    after = _component_snapshot(component)
    if before != after:
        record_audit_event(
            company=company,
            area=AuditArea.INTERNAL,
            action="internal.salary_component.updated",
            object_type="internal_payroll.SalaryComponent",
            object_id=component.pk,
            object_label=str(component),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return component


@transaction.atomic
def create_overtime_policy(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    base_component_id,
    divisor: object,
    multiplier: object,
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> OvertimePolicy:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    if not base_component_id:
        raise ValidationError({"base_component": "Overtime base component is required."})
    base_component = SalaryComponent.objects.select_for_update().for_company(company).get(pk=base_component_id)
    if not base_component.is_active or base_component.archived_at:
        raise ValidationError({"base_component": "Overtime base component must be active and not archived."})
    code = code.strip() or allocate_number(company=company, key="internal.overtime_policy", prefix="OT-", padding=4)
    policy = OvertimePolicy(
        company=company,
        code=code,
        name=name,
        base_component=base_component,
        divisor=_rate(divisor, "divisor"),
        multiplier=_rate(multiplier, "multiplier"),
        notes=notes,
        is_active=_active_flag(is_active),
    )
    policy.full_clean()
    try:
        policy.save()
    except IntegrityError as exc:
        raise ValidationError("Overtime policy code and name must be unique within the company.") from exc
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.overtime_policy.created",
        object_type="internal_payroll.OvertimePolicy",
        object_id=policy.pk,
        object_label=str(policy),
        actor_membership=actor_membership,
        after=_policy_snapshot(policy),
        request=request,
    )
    return policy


@transaction.atomic
def update_overtime_policy(
    *,
    actor_membership: CompanyMembership,
    policy_id,
    code: str,
    name: str,
    base_component_id,
    divisor: object,
    multiplier: object,
    notes: str = "",
    is_active: bool | str = True,
    request: HttpRequest | None = None,
) -> OvertimePolicy:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    policy = OvertimePolicy.objects.select_for_update().select_related("base_component").get(pk=policy_id, company=company)
    if policy.archived_at:
        raise ValidationError({"policy": "Restore the archived overtime policy before editing it."})
    if not base_component_id:
        raise ValidationError({"base_component": "Overtime base component is required."})
    base_component = SalaryComponent.objects.select_for_update().for_company(company).get(pk=base_component_id)
    if not base_component.is_active or base_component.archived_at:
        raise ValidationError({"base_component": "Overtime base component must be active and not archived."})
    before = _policy_snapshot(policy)
    policy.code = code
    policy.name = name
    policy.base_component = base_component
    policy.divisor = _rate(divisor, "divisor")
    policy.multiplier = _rate(multiplier, "multiplier")
    policy.notes = notes
    policy.is_active = _active_flag(is_active)
    policy.full_clean()
    try:
        policy.save()
    except IntegrityError as exc:
        raise ValidationError("Overtime policy code and name must be unique within the company.") from exc
    after = _policy_snapshot(policy)
    if before != after:
        record_audit_event(
            company=company,
            area=AuditArea.INTERNAL,
            action="internal.overtime_policy.updated",
            object_type="internal_payroll.OvertimePolicy",
            object_id=policy.pk,
            object_label=str(policy),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return policy



@transaction.atomic
def archive_salary_component(*, actor_membership: CompanyMembership, component_id, reason: str, request: HttpRequest | None = None) -> SalaryComponent:
    _require_internal_edit(actor_membership)
    component = SalaryComponent.objects.select_for_update().for_company(actor_membership.company).get(pk=component_id)
    if component.archived_at:
        return component
    decision = require_lifecycle_action(component, LifecycleAction.ARCHIVE, reason=reason)
    before = _component_snapshot(component)
    component.is_active = False
    component.archived_at = timezone.now()
    component.archived_reason = (reason or "").strip()
    component.full_clean()
    component.save(update_fields=["is_active", "archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(instance=component, decision=decision, actor_membership=actor_membership, before=before, after=_component_snapshot(component), reason=reason, audit_action="internal.salary_component.archived", request=request)
    return component


@transaction.atomic
def restore_salary_component_archive(*, actor_membership: CompanyMembership, component_id, reason: str = "", request: HttpRequest | None = None) -> SalaryComponent:
    _require_internal_edit(actor_membership)
    component = SalaryComponent.objects.select_for_update().for_company(actor_membership.company).get(pk=component_id)
    if not component.archived_at:
        return component
    decision = require_lifecycle_action(component, LifecycleAction.RESTORE)
    before = _component_snapshot(component); previous_reason = component.archived_reason
    component.archived_at = None
    component.archived_reason = ""
    component.is_active = False
    component.full_clean()
    component.save(update_fields=["archived_at", "archived_reason", "is_active", "updated_at"])
    record_lifecycle_action(instance=component, decision=decision, actor_membership=actor_membership, before=before, after=_component_snapshot(component), reason=reason, audit_action="internal.salary_component.archive_restored", metadata={"previous_archive_reason": previous_reason, "restored_status": "inactive"}, request=request)
    return component


@transaction.atomic
def delete_unused_salary_component(*, actor_membership: CompanyMembership, component_id, confirmation: str, reason: str = "", request: HttpRequest | None = None) -> str:
    _require_internal_edit(actor_membership)
    component = SalaryComponent.objects.select_for_update().for_company(actor_membership.company).get(pk=component_id)
    decision = require_lifecycle_action(component, LifecycleAction.DELETE, confirmation=confirmation)
    before = _component_snapshot(component); object_id = str(component.pk); object_label = str(component)
    try:
        component.delete()
    except ProtectedError as exc:
        raise ValidationError({"component": "This salary component is referenced by protected payroll history. Archive it instead."}) from exc
    record_lifecycle_action(instance=component, decision=decision, actor_membership=actor_membership, before=before, after={}, reason=reason, audit_action="internal.salary_component.deleted_unused", object_id=object_id, object_label=object_label, metadata={"guard": "unused-master-only"}, request=request)
    return object_id


@transaction.atomic
def archive_overtime_policy(*, actor_membership: CompanyMembership, policy_id, reason: str, request: HttpRequest | None = None) -> OvertimePolicy:
    _require_internal_edit(actor_membership)
    policy = OvertimePolicy.objects.select_for_update().select_related("base_component").for_company(actor_membership.company).get(pk=policy_id)
    if policy.archived_at:
        return policy
    decision = require_lifecycle_action(policy, LifecycleAction.ARCHIVE, reason=reason)
    before = _policy_snapshot(policy)
    policy.is_active = False
    policy.archived_at = timezone.now()
    policy.archived_reason = (reason or "").strip()
    policy.full_clean()
    policy.save(update_fields=["is_active", "archived_at", "archived_reason", "updated_at"])
    record_lifecycle_action(instance=policy, decision=decision, actor_membership=actor_membership, before=before, after=_policy_snapshot(policy), reason=reason, audit_action="internal.overtime_policy.archived", request=request)
    return policy


@transaction.atomic
def restore_overtime_policy_archive(*, actor_membership: CompanyMembership, policy_id, reason: str = "", request: HttpRequest | None = None) -> OvertimePolicy:
    _require_internal_edit(actor_membership)
    policy = OvertimePolicy.objects.select_for_update().select_related("base_component").for_company(actor_membership.company).get(pk=policy_id)
    if not policy.archived_at:
        return policy
    decision = require_lifecycle_action(policy, LifecycleAction.RESTORE)
    before = _policy_snapshot(policy); previous_reason = policy.archived_reason
    policy.archived_at = None
    policy.archived_reason = ""
    policy.is_active = False
    policy.full_clean()
    policy.save(update_fields=["archived_at", "archived_reason", "is_active", "updated_at"])
    record_lifecycle_action(instance=policy, decision=decision, actor_membership=actor_membership, before=before, after=_policy_snapshot(policy), reason=reason, audit_action="internal.overtime_policy.archive_restored", metadata={"previous_archive_reason": previous_reason, "restored_status": "inactive"}, request=request)
    return policy


@transaction.atomic
def delete_unused_overtime_policy(*, actor_membership: CompanyMembership, policy_id, confirmation: str, reason: str = "", request: HttpRequest | None = None) -> str:
    _require_internal_edit(actor_membership)
    policy = OvertimePolicy.objects.select_for_update().select_related("base_component").for_company(actor_membership.company).get(pk=policy_id)
    decision = require_lifecycle_action(policy, LifecycleAction.DELETE, confirmation=confirmation)
    before = _policy_snapshot(policy); object_id = str(policy.pk); object_label = str(policy)
    try:
        policy.delete()
    except ProtectedError as exc:
        raise ValidationError({"policy": "This overtime policy is referenced by protected salary history. Archive it instead."}) from exc
    record_lifecycle_action(instance=policy, decision=decision, actor_membership=actor_membership, before=before, after={}, reason=reason, audit_action="internal.overtime_policy.deleted_unused", object_id=object_id, object_label=object_label, metadata={"guard": "unused-master-only"}, request=request)
    return object_id


@transaction.atomic
def assign_employee_salary_structure(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    effective_from: date,
    components: list[dict[str, object]],
    overtime_policy_id=None,
    notes: str = "",
    request: HttpRequest | None = None,
) -> SalaryStructure:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    if not employee_id:
        raise ValidationError({"employee": "Employee is required."})
    employee = InternalEmployee.objects.select_for_update().get(pk=employee_id, company=company)

    if effective_from < employee.joining_date:
        raise ValidationError({"effective_from": "Salary structure cannot start before the employee joining date."})
    if employee.employment_end_date and effective_from > employee.employment_end_date:
        raise ValidationError({"effective_from": "Salary structure cannot start after the employee employment end date."})

    existing_structures = list(
        SalaryStructure.objects.select_for_update()
        .filter(company=company, employee=employee)
        .order_by("effective_from", "created_at")
    )
    if any(item.effective_from == effective_from for item in existing_structures):
        raise ValidationError({"effective_from": "A salary structure already starts on this date. Choose a new effective date."})

    if not isinstance(components, list) or not components:
        raise ValidationError({"components": "At least one recurring salary component is required."})

    normalized_input: dict[str, Decimal] = {}
    for index, item in enumerate(components):
        if not isinstance(item, dict):
            raise ValidationError({"components": f"Component row {index + 1} is invalid."})
        component_id = str(item.get("component_id") or item.get("id") or "").strip()
        if not component_id:
            raise ValidationError({"components": f"Component row {index + 1} is missing its component ID."})
        if component_id in normalized_input:
            raise ValidationError({"components": "The same salary component cannot appear more than once."})
        normalized_input[component_id] = _money(item.get("amount", 0), "components")

    overtime_policy = None
    if overtime_policy_id:
        overtime_policy = (
            OvertimePolicy.objects.select_for_update()
            .for_company(company)
            .select_related("base_component")
            .get(pk=overtime_policy_id, is_active=True, archived_at__isnull=True)
        )

    component_rows = list(
        SalaryComponent.objects.select_for_update()
        .for_company(company)
        .filter(pk__in=list(normalized_input), is_active=True, archived_at__isnull=True)
        .order_by("code")
    )
    if len(component_rows) != len(normalized_input):
        raise ValidationError({"components": "Every salary component must exist, be active, and belong to the active company."})
    if any(item.recurrence != SalaryComponentRecurrence.RECURRING for item in component_rows):
        raise ValidationError({"components": "Only recurring components can be stored in a permanent salary structure."})

    basic_rows = [item for item in component_rows if item.wps_mapping == WPSMapping.BASIC_SALARY]
    if len(basic_rows) != 1:
        raise ValidationError({"components": "Exactly one active recurring earning component must be mapped as Basic Salary."})
    basic_amount = normalized_input[str(basic_rows[0].pk)]
    if basic_amount <= Decimal("0"):
        raise ValidationError({"components": "Basic Salary must be greater than zero."})

    if overtime_policy is not None:
        base_key = str(overtime_policy.base_component_id)
        if base_key not in normalized_input or normalized_input[base_key] <= Decimal("0"):
            raise ValidationError({"overtime_policy": "The overtime base component must be included with a positive amount in the salary structure."})

    previous = None
    next_structure = None
    for item in existing_structures:
        if item.effective_from < effective_from:
            previous = item
        elif item.effective_from > effective_from:
            next_structure = item
            break

    if previous is not None and (previous.effective_to is None or previous.effective_to >= effective_from):
        previous_effective_to = previous.effective_to
        previous.effective_to = effective_from - timedelta(days=1)
        previous.full_clean()
        previous.save(update_fields=("effective_to", "updated_at"))
        record_audit_event(
            company=company,
            area=AuditArea.INTERNAL,
            action="internal.salary_structure.closed",
            object_type="internal_payroll.SalaryStructure",
            object_id=previous.pk,
            object_label=str(previous),
            actor_membership=actor_membership,
            before={
                "effective_from": previous.effective_from.isoformat(),
                "effective_to": previous_effective_to.isoformat() if previous_effective_to else None,
            },
            after={
                "effective_from": previous.effective_from.isoformat(),
                "effective_to": previous.effective_to.isoformat(),
            },
            metadata={
                "employee_number": employee.employee_number,
                "superseded_by_effective_from": effective_from.isoformat(),
            },
            request=request,
        )

    structure = SalaryStructure(
        company=company,
        employee=employee,
        effective_from=effective_from,
        effective_to=(next_structure.effective_from - timedelta(days=1)) if next_structure else None,
        overtime_policy=overtime_policy,
        overtime_policy_code=overtime_policy.code if overtime_policy else "",
        overtime_policy_name=overtime_policy.name if overtime_policy else "",
        overtime_base_component_code=overtime_policy.base_component.code if overtime_policy else "",
        overtime_base_component_name=overtime_policy.base_component.name if overtime_policy else "",
        overtime_divisor=overtime_policy.divisor if overtime_policy else None,
        overtime_multiplier=overtime_policy.multiplier if overtime_policy else None,
        notes=notes,
    )
    structure.full_clean()
    try:
        structure.save()
    except IntegrityError as exc:
        raise ValidationError("The effective salary structure conflicts with an existing employee salary period.") from exc

    lines: list[SalaryStructureLine] = []
    for component in component_rows:
        line = SalaryStructureLine(
            company=company,
            structure=structure,
            component=component,
            amount=normalized_input[str(component.pk)],
            component_code=component.code,
            component_name=component.name,
            component_category=component.category,
            component_recurrence=component.recurrence,
            component_calculation=component.calculation,
            wps_mapping=component.wps_mapping,
        )
        line.full_clean()
        line.save()
        lines.append(line)

    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_structure.assigned",
        object_type="internal_payroll.SalaryStructure",
        object_id=structure.pk,
        object_label=str(structure),
        actor_membership=actor_membership,
        after=_structure_snapshot(structure, lines),
        metadata={"employee_number": employee.employee_number},
        request=request,
    )
    return structure
