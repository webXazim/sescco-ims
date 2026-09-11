from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.core.query_controls import apply_ordering, parse_list_controls, serialize_list
from apps.internal_payroll.api_utils import (
    handle_api_error as _handle_error,
    json_body as _json_body,
    parse_active_query as _active_query,
    parse_date as _date,
    parse_optional_date as _optional_date,
)
from apps.internal_payroll.models import Branch, Department, EmploymentStatus, InternalEmployee
from apps.internal_payroll.selectors import (
    branches_for_company,
    departments_for_company,
    employees_for_company,
    serialize_branch,
    serialize_department,
    serialize_employee,
)
from apps.internal_payroll.selectors.organization import serialize_assignment
from apps.internal_payroll.services import (
    change_employee_organization,
    create_branch,
    create_department,
    create_employee,
    update_branch,
    update_department,
    update_employee,
)


def _employee_status_query(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized or normalized == "all":
        return ""
    allowed = {item.value for item in EmploymentStatus}
    if normalized not in allowed:
        raise ValidationError({"status": "Unknown employee status."})
    return normalized


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def branches_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {
                "code": "code",
                "name": "name",
                "location": "location",
                "manager": "manager_name",
                "status": "is_active",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="code")
            rows = branches_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                active=_active_query(request.GET.get("status", "")),
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_branch)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        branch = create_branch(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            location=str(body.get("location", "")),
            address=str(body.get("address", "")),
            manager_name=str(body.get("manager", "")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        return JsonResponse({"ok": True, "branch": serialize_branch(branch)}, status=201)
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def branch_detail_api(request: HttpRequest, branch_id) -> JsonResponse:
    try:
        body = _json_body(request)
        current = Branch.objects.for_company(request.company).get(pk=branch_id)
        branch = update_branch(
            actor_membership=request.company_membership,
            branch_id=branch_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            location=str(body.get("location", current.location)),
            address=str(body.get("address", current.address)),
            manager_name=str(body.get("manager", current.manager_name)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        return JsonResponse({"ok": True, "branch": serialize_branch(branch)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def departments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {"code": "code", "name": "name", "status": "is_active"}
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="code")
            rows = departments_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                active=_active_query(request.GET.get("status", "")),
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_department)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        department = create_department(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            notes=str(body.get("notes", "")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        return JsonResponse({"ok": True, "department": serialize_department(department)}, status=201)
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def department_detail_api(request: HttpRequest, department_id) -> JsonResponse:
    try:
        body = _json_body(request)
        current = Department.objects.for_company(request.company).get(pk=department_id)
        department = update_department(
            actor_membership=request.company_membership,
            department_id=department_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            notes=str(body.get("notes", current.notes)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        return JsonResponse({"ok": True, "department": serialize_department(department)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def employees_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {
                "employee": "employee_number",
                "name": "full_name",
                "joining": "joining_date",
                "status": "status",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="employee")
            rows = employees_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                status=_employee_status_query(request.GET.get("status", "")),
                branch_id=request.GET.get("branch") or None,
                department_id=request.GET.get("department") or None,
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_employee)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        employee = create_employee(
            actor_membership=request.company_membership,
            employee_number=str(body.get("employee_number", "")),
            full_name=str(body.get("full_name", "")),
            joining_date=_date(body.get("joining_date"), "joining_date"),
            branch_id=body.get("branch_id"),
            department_id=body.get("department_id"),
            position=str(body.get("position", "")),
            status=str(body.get("status", "Active")),
            national_id=str(body.get("national_id", "")),
            phone=str(body.get("phone", "")),
            employment_end_date=_optional_date(body.get("employment_end_date"), "employment_end_date"),
            request=request,
        )
        employee = employees_for_company(company=request.company).get(pk=employee.pk)
        history = employee.organization_history
        return JsonResponse(
            {
                "ok": True,
                "employee": serialize_employee(employee),
                "history": [serialize_assignment(item) for item in history],
            },
            status=201,
        )
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def employee_detail_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = _json_body(request)
        employee = InternalEmployee.objects.for_company(request.company).get(pk=employee_id)
        employee = update_employee(
            actor_membership=request.company_membership,
            employee_id=employee_id,
            employee_number=str(body.get("employee_number", employee.employee_number)),
            full_name=str(body.get("full_name", employee.full_name)),
            joining_date=_date(body.get("joining_date", employee.joining_date.isoformat()), "joining_date"),
            status=str(body.get("status", employee.status)),
            national_id=str(body.get("national_id", employee.national_id)),
            phone=str(body.get("phone", employee.phone)),
            employment_end_date=_optional_date(
                body.get("employment_end_date", employee.employment_end_date.isoformat() if employee.employment_end_date else None),
                "employment_end_date",
            ),
            request=request,
        )
        employee = employees_for_company(company=request.company).get(pk=employee.pk)
        return JsonResponse({"ok": True, "employee": serialize_employee(employee)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def employee_organization_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = _json_body(request)
        assignment = change_employee_organization(
            actor_membership=request.company_membership,
            employee_id=employee_id,
            branch_id=body.get("branch_id"),
            department_id=body.get("department_id"),
            position=str(body.get("position", "")),
            effective_from=_date(body.get("effective_from"), "effective_from"),
            reason=str(body.get("reason", "Organization change")),
            request=request,
        )
        employee = employees_for_company(company=request.company).get(pk=employee_id)
        history = employee.organization_history
        return JsonResponse(
            {
                "ok": True,
                "employee": serialize_employee(employee),
                "assignment": serialize_assignment(assignment),
                "history": [serialize_assignment(item) for item in history],
            },
            status=201,
        )
    except Exception as exc:
        return _handle_error(exc)
