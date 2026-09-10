from __future__ import annotations

from datetime import date

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.core.models import Company
from apps.internal_payroll.models import (
    OvertimePolicy,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureLine,
    WPSMapping,
)


def salary_components_for_company(
    *,
    company: Company,
    query: str = "",
    active: bool | None = None,
    category: str = "",
) -> QuerySet[SalaryComponent]:
    rows = SalaryComponent.objects.for_company(company)
    if active is not None:
        rows = rows.filter(is_active=active)
    if category:
        rows = rows.filter(category=category)
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(notes__icontains=query)
            | Q(wps_mapping__icontains=query)
        )
    return rows.order_by("category", "code", "name")


def overtime_policies_for_company(
    *,
    company: Company,
    query: str = "",
    active: bool | None = None,
) -> QuerySet[OvertimePolicy]:
    rows = OvertimePolicy.objects.for_company(company).select_related("base_component")
    if active is not None:
        rows = rows.filter(is_active=active)
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(base_component__code__icontains=query)
            | Q(base_component__name__icontains=query)
            | Q(notes__icontains=query)
        )
    return rows.order_by("code", "name")


def salary_structures_for_company(
    *,
    company: Company,
    employee_id=None,
) -> QuerySet[SalaryStructure]:
    lines = SalaryStructureLine.objects.for_company(company).select_related("component").order_by(
        "component_category", "component_code"
    )
    rows = SalaryStructure.objects.for_company(company).select_related(
        "employee", "overtime_policy"
    ).prefetch_related(Prefetch("lines", queryset=lines, to_attr="salary_lines"))
    if employee_id:
        rows = rows.filter(employee_id=employee_id)
    return rows.order_by("employee__employee_number", "-effective_from", "-created_at")


def current_salary_structures_for_company(
    *,
    company: Company,
    as_of: date | None = None,
) -> QuerySet[SalaryStructure]:
    as_of = as_of or timezone.localdate()
    return (
        salary_structures_for_company(company=company)
        .filter(effective_from__lte=as_of)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
        .filter(Q(employee__employment_end_date__isnull=True) | Q(employee__employment_end_date__gte=as_of))
    )


def serialize_salary_component(component: SalaryComponent) -> dict[str, object]:
    return {
        "id": str(component.pk),
        "code": component.code,
        "name": component.name,
        "category": component.get_category_display(),
        "recurrence": component.get_recurrence_display(),
        "calculation": component.get_calculation_display(),
        "wpsMap": component.get_wps_mapping_display(),
        "status": "Active" if component.is_active else "Inactive",
        "notes": component.notes,
    }


def serialize_overtime_policy(policy: OvertimePolicy) -> dict[str, object]:
    return {
        "id": str(policy.pk),
        "code": policy.code,
        "name": policy.name,
        "baseComponentId": str(policy.base_component_id),
        "baseComponent": policy.base_component.name,
        "divisor": str(policy.divisor),
        "multiplier": str(policy.multiplier),
        "status": "Active" if policy.is_active else "Inactive",
        "notes": policy.notes,
    }


def _lines_for_structure(structure: SalaryStructure) -> list[SalaryStructureLine]:
    prefetched = getattr(structure, "salary_lines", None)
    if prefetched is not None:
        return list(prefetched)
    return list(structure.lines.select_related("component").order_by("component_category", "component_code"))


def serialize_salary_structure(structure: SalaryStructure) -> dict[str, object]:
    lines = _lines_for_structure(structure)
    return {
        "id": str(structure.pk),
        "employeeId": str(structure.employee_id),
        "effective": structure.effective_from.isoformat(),
        "effectiveTo": structure.effective_to.isoformat() if structure.effective_to else None,
        "source": "Managed salary structure",
        "components": [
            {
                "id": str(line.component_id),
                "code": line.component_code,
                "name": line.component_name,
                "type": line.component_category,
                "recurrence": line.component_recurrence,
                "calculation": line.component_calculation,
                "wpsMap": WPSMapping(line.wps_mapping).label,
                "amount": str(line.amount),
            }
            for line in lines
        ],
        "otPolicyId": str(structure.overtime_policy_id) if structure.overtime_policy_id else None,
        "otPolicy": structure.overtime_policy_name or "No overtime policy",
        "otPolicySnapshot": (
            {
                "code": structure.overtime_policy_code,
                "name": structure.overtime_policy_name,
                "baseComponent": structure.overtime_base_component_name,
                "baseComponentCode": structure.overtime_base_component_code,
                "divisor": str(structure.overtime_divisor),
                "multiplier": str(structure.overtime_multiplier),
            }
            if structure.overtime_policy_name
            else None
        ),
        "notes": structure.notes,
    }


def salary_setup_context(*, company: Company, as_of: date | None = None) -> dict[str, object]:
    components = list(salary_components_for_company(company=company))
    policies = list(overtime_policies_for_company(company=company))
    structures = list(salary_structures_for_company(company=company))
    as_of = as_of or timezone.localdate()

    current_by_employee: dict[str, dict[str, object]] = {}
    history_by_employee: dict[str, list[dict[str, object]]] = {}
    for structure in structures:
        employee_key = str(structure.employee_id)
        serialized = serialize_salary_structure(structure)
        history_by_employee.setdefault(employee_key, []).append(serialized)
        employee_is_employed = (
            structure.employee.employment_end_date is None
            or structure.employee.employment_end_date >= as_of
        )
        if (
            employee_key not in current_by_employee
            and employee_is_employed
            and structure.effective_from <= as_of
            and (structure.effective_to is None or structure.effective_to >= as_of)
        ):
            current_by_employee[employee_key] = serialized

    return {
        "salaryComponents": [serialize_salary_component(item) for item in components],
        "overtimePolicies": [serialize_overtime_policy(item) for item in policies],
        "salaryStructures": current_by_employee,
        "salaryStructureHistory": history_by_employee,
        "asOf": as_of.isoformat(),
    }
