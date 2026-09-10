from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import (
    handle_api_error,
    json_body,
    parse_active_query,
    parse_date,
)
from apps.internal_payroll.models import OvertimePolicy, SalaryComponent, SalaryComponentCategory
from apps.internal_payroll.selectors import (
    overtime_policies_for_company,
    salary_components_for_company,
    salary_structures_for_company,
    serialize_overtime_policy,
    serialize_salary_component,
    serialize_salary_structure,
)
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    create_overtime_policy,
    create_salary_component,
    update_overtime_policy,
    update_salary_component,
)


def _category_query(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or normalized == "all":
        return ""
    if normalized in {SalaryComponentCategory.EARNING, SalaryComponentCategory.DEDUCTION}:
        return normalized
    raise ValidationError({"category": "Category must be Earning, Deduction, or All."})


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_components_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            rows = salary_components_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                active=parse_active_query(request.GET.get("status", "")),
                category=_category_query(request.GET.get("category", "")),
            )
            return JsonResponse({"ok": True, "results": [serialize_salary_component(item) for item in rows]})

        body = json_body(request)
        component = create_salary_component(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            category=str(body.get("category", "")),
            recurrence=str(body.get("recurrence", "")),
            calculation=str(body.get("calculation", "")),
            wps_mapping=str(body.get("wps_mapping", body.get("wpsMap", "Not mapped"))),
            notes=str(body.get("notes", "")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        return JsonResponse({"ok": True, "component": serialize_salary_component(component)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def salary_component_detail_api(request: HttpRequest, component_id) -> JsonResponse:
    try:
        body = json_body(request)
        current = SalaryComponent.objects.for_company(request.company).get(pk=component_id)
        component = update_salary_component(
            actor_membership=request.company_membership,
            component_id=component_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            category=str(body.get("category", current.get_category_display())),
            recurrence=str(body.get("recurrence", current.get_recurrence_display())),
            calculation=str(body.get("calculation", current.get_calculation_display())),
            wps_mapping=str(body.get("wps_mapping", body.get("wpsMap", current.get_wps_mapping_display()))),
            notes=str(body.get("notes", current.notes)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        return JsonResponse({"ok": True, "component": serialize_salary_component(component)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def overtime_policies_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            rows = overtime_policies_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                active=parse_active_query(request.GET.get("status", "")),
            )
            return JsonResponse({"ok": True, "results": [serialize_overtime_policy(item) for item in rows]})

        body = json_body(request)
        policy = create_overtime_policy(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            base_component_id=body.get("base_component_id"),
            divisor=body.get("divisor"),
            multiplier=body.get("multiplier"),
            notes=str(body.get("notes", "")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        policy = OvertimePolicy.objects.for_company(request.company).select_related("base_component").get(pk=policy.pk)
        return JsonResponse({"ok": True, "policy": serialize_overtime_policy(policy)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def overtime_policy_detail_api(request: HttpRequest, policy_id) -> JsonResponse:
    try:
        body = json_body(request)
        current = OvertimePolicy.objects.for_company(request.company).select_related("base_component").get(pk=policy_id)
        policy = update_overtime_policy(
            actor_membership=request.company_membership,
            policy_id=policy_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            base_component_id=body.get("base_component_id", current.base_component_id),
            divisor=body.get("divisor", current.divisor),
            multiplier=body.get("multiplier", current.multiplier),
            notes=str(body.get("notes", current.notes)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        policy = OvertimePolicy.objects.for_company(request.company).select_related("base_component").get(pk=policy.pk)
        return JsonResponse({"ok": True, "policy": serialize_overtime_policy(policy)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_structures_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            rows = salary_structures_for_company(
                company=request.company,
                employee_id=request.GET.get("employee") or None,
            )
            return JsonResponse({"ok": True, "results": [serialize_salary_structure(item) for item in rows]})

        body = json_body(request)
        raw_components = body.get("components", [])
        if not isinstance(raw_components, list):
            raise ValidationError({"components": "Components must be a list."})
        structure = assign_employee_salary_structure(
            actor_membership=request.company_membership,
            employee_id=body.get("employee_id"),
            effective_from=parse_date(body.get("effective_from"), "effective_from"),
            components=raw_components,
            overtime_policy_id=body.get("overtime_policy_id") or None,
            notes=str(body.get("notes", "")),
            request=request,
        )
        rows = list(salary_structures_for_company(company=request.company, employee_id=structure.employee_id))
        history = [serialize_salary_structure(item) for item in rows]
        today = timezone.localdate()
        current = next(
            (
                serialized
                for item, serialized in zip(rows, history)
                if item.effective_from <= today
                and (item.effective_to is None or item.effective_to >= today)
                and (item.employee.employment_end_date is None or item.employee.employment_end_date >= today)
            ),
            None,
        )
        created = serialize_salary_structure(next(item for item in rows if item.pk == structure.pk))
        return JsonResponse(
            {
                "ok": True,
                "structure": created,
                "current": current,
                "history": history,
            },
            status=201,
        )
    except Exception as exc:
        return handle_api_error(exc)
