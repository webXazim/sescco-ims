from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.core.query_controls import apply_ordering, parse_list_controls, serialize_list

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.api_permissions import api_method_access_required, api_workspace_required
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import (
    handle_api_error,
    json_body,
    parse_date,
)
from apps.internal_payroll.models import OvertimePolicy, SalaryComponent, SalaryComponentCategory
from apps.internal_payroll.selectors import (
    current_salary_structures_for_company,
    employees_for_company,
    overtime_policies_for_company,
    salary_components_for_company,
    salary_structures_for_company,
    serialize_employee,
    serialize_overtime_policy,
    serialize_salary_component,
    serialize_salary_structure,
)
from apps.internal_payroll.services import (
    archive_overtime_policy,
    archive_salary_component,
    assign_employee_salary_structure,
    create_overtime_policy,
    create_salary_component,
    delete_unused_overtime_policy,
    delete_unused_salary_component,
    restore_overtime_policy_archive,
    restore_salary_component_archive,
    update_overtime_policy,
    update_salary_component,
)


def _configuration_status(value: str) -> tuple[bool | None, bool | None]:
    normalized = (value or "").strip().lower()
    if not normalized or normalized == "all":
        return None, None
    if normalized == "active":
        return True, False
    if normalized == "inactive":
        return False, False
    if normalized == "archived":
        return None, True
    raise ValidationError({"status": "Status must be Active, Inactive, Archived, or All."})


def _category_query(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or normalized == "all":
        return ""
    if normalized in {SalaryComponentCategory.EARNING, SalaryComponentCategory.DEDUCTION}:
        return normalized
    raise ValidationError({"category": "Category must be Earning, Deduction, or All."})


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_SALARY_SETUP_VIEW, POST=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def salary_components_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            active, archived = _configuration_status(request.GET.get("status", ""))
            rows = salary_components_for_company(
                company=request.company, query=request.GET.get("q", ""), active=active, archived=archived,
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


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(PATCH=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE, DELETE=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def salary_component_detail_api(request: HttpRequest, component_id) -> JsonResponse:
    try:
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_salary_component(
                actor_membership=request.company_membership, component_id=component_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedComponentId": deleted_id})
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


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def salary_component_lifecycle_api(request: HttpRequest, component_id) -> JsonResponse:
    try:
        body = json_body(request); action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            component = archive_salary_component(actor_membership=request.company_membership, component_id=component_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            component = restore_salary_component_archive(actor_membership=request.company_membership, component_id=component_id, reason=str(body.get("reason", "")), request=request)
        else:
            raise ValidationError({"action": "Salary component lifecycle action must be archive or restore."})
        return JsonResponse({"ok": True, "component": serialize_salary_component(component)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_SALARY_SETUP_VIEW, POST=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def overtime_policies_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            active, archived = _configuration_status(request.GET.get("status", ""))
            rows = overtime_policies_for_company(
                company=request.company, query=request.GET.get("q", ""), active=active, archived=archived,
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


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(PATCH=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE, DELETE=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def overtime_policy_detail_api(request: HttpRequest, policy_id) -> JsonResponse:
    try:
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_overtime_policy(
                actor_membership=request.company_membership, policy_id=policy_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedPolicyId": deleted_id})
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


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def overtime_policy_lifecycle_api(request: HttpRequest, policy_id) -> JsonResponse:
    try:
        body = json_body(request); action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            policy = archive_overtime_policy(actor_membership=request.company_membership, policy_id=policy_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            policy = restore_overtime_policy_archive(actor_membership=request.company_membership, policy_id=policy_id, reason=str(body.get("reason", "")), request=request)
        else:
            raise ValidationError({"action": "Overtime policy lifecycle action must be archive or restore."})
        policy = OvertimePolicy.objects.for_company(request.company).select_related("base_component").get(pk=policy.pk)
        return JsonResponse({"ok": True, "policy": serialize_overtime_policy(policy)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_SALARY_SETUP_VIEW, POST=AccessPermission.INTERNAL_SALARY_SETUP_MANAGE)
def salary_structures_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            employee_id = request.GET.get("employee") or None
            if employee_id:
                rows = list(salary_structures_for_company(company=request.company, employee_id=employee_id))
                history = [serialize_salary_structure(item) for item in rows]
                as_of = timezone.localdate()
                current = next(
                    (
                        serialized
                        for item, serialized in zip(rows, history)
                        if item.effective_from <= as_of
                        and (item.effective_to is None or item.effective_to >= as_of)
                        and (item.employee.employment_end_date is None or item.employee.employment_end_date >= as_of)
                    ),
                    None,
                )
                return JsonResponse({"ok": True, "results": history, "history": history, "current": current})

            # 1.0.72: Employee Structures is an employee-first directory. Paginate the
            # employee population before loading salary lines so 2,000 employees do not
            # serialize every current/historical structure just to open Salary Setup.
            allowed_sorts = {
                "employee": "employee_number",
                "name": "full_name",
                "joining": "joining_date",
                "status": "status",
            }
            controls = parse_list_controls(
                request, allowed_sorts=allowed_sorts, default_sort="employee", max_page_size=100
            )
            if controls.page is None or controls.page_size is None:
                # The list endpoint is intentionally bounded even when an older caller
                # omits pagination controls. Employee-specific history remains available
                # through ?employee=<uuid>.
                from apps.core.query_controls import ListControls
                controls = ListControls(sort=controls.sort, direction=controls.direction, page=1, page_size=50)

            employees = employees_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                archived=False,
            )
            current_structures = current_salary_structures_for_company(company=request.company)
            setup = str(request.GET.get("setup", "all")).strip().lower().replace(" ", "_")
            if setup in {"configured", "ready"}:
                employees = employees.filter(pk__in=current_structures.values("employee_id"))
            elif setup in {"needs_setup", "missing"}:
                employees = employees.exclude(pk__in=current_structures.values("employee_id"))
            elif setup not in {"", "all"}:
                raise ValidationError({"setup": "Setup filter must be configured, needs_setup, or all."})

            employees = apply_ordering(employees, controls=controls, allowed_sorts=allowed_sorts)
            employee_results, meta = serialize_list(employees, controls=controls, serializer=serialize_employee)
            page_ids = [row["id"] for row in employee_results]
            structures = current_salary_structures_for_company(company=request.company).filter(employee_id__in=page_ids)
            current_by_employee = {}
            for structure in structures:
                key = str(structure.employee_id)
                if key not in current_by_employee:
                    current_by_employee[key] = serialize_salary_structure(structure)

            results = [
                {"employee": employee, "structure": current_by_employee.get(str(employee["id"]))}
                for employee in employee_results
            ]
            coverage_employees = employees_for_company(company=request.company, archived=False)
            employee_count = coverage_employees.count()
            configured_count = (
                current_salary_structures_for_company(company=request.company)
                .filter(employee_id__in=coverage_employees.values("pk"))
                .values("employee_id")
                .distinct()
                .count()
            )
            meta["coverage"] = {
                "employeeCount": int(employee_count),
                "configuredCount": int(configured_count),
                "needsSetupCount": max(0, int(employee_count) - int(configured_count)),
            }
            return JsonResponse({"ok": True, "results": results, "meta": meta})

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
