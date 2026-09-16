from __future__ import annotations

from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.api_permissions import api_method_access_required, api_workspace_required
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import handle_api_error, json_body
from apps.internal_payroll.models import AttendanceEntry, AttendanceOvertimeEntry
from apps.internal_payroll.selectors import attendance_period_context
from apps.internal_payroll.selectors.attendance import attendance_period_summary, serialize_attendance_period
from apps.internal_payroll.services import (
    import_attendance_rows,
    save_attendance_entries,
    save_overtime_entries,
    transition_attendance_period,
)


def _period_start(value: str) -> date:
    normalized = value.strip()
    if len(normalized) == 7:
        normalized = f"{normalized}-01"
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    if parsed.day != 1:
        raise ValidationError({"period": "Period must identify a calendar month."})
    return parsed


def _request_period(request: HttpRequest, body: dict[str, object] | None = None) -> date:
    raw = request.GET.get("period", "")
    if not raw and body is not None:
        raw = str(body.get("period") or "")
    if not raw:
        raise ValidationError({"period": "Period is required in YYYY-MM format."})
    return _period_start(raw)


def _require_action_permission(request: HttpRequest, permission: AccessPermission) -> None:
    if not membership_has_permission(request.company_membership, permission):
        raise PermissionDenied("Your access profile does not allow this attendance workflow action.")


def _bounded_page(request: HttpRequest) -> tuple[int, int]:
    try:
        page = max(1, int(request.GET.get("page") or 1))
        page_size = int(request.GET.get("page_size") or 50)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"page": "page and page_size must be positive integers."}) from exc
    if page_size not in {25, 50, 100}:
        raise ValidationError({"page_size": "page_size must be 25, 50, or 100."})
    return page, page_size


def _attendance_delta(*, company, period, raw_entries: list[dict[str, object]], membership=None) -> dict[str, object]:
    requested: list[tuple[str, date]] = []
    for item in raw_entries:
        employee_id = str(item.get("employee_id") or "")
        raw_date = item.get("date")
        work_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
        requested.append((employee_id, work_date))
    employee_ids = {employee_id for employee_id, _work_date in requested}
    work_dates = {work_date for _employee_id, work_date in requested}
    saved = {
        (str(row.employee_id), row.work_date): (row.code or (str(int(row.regular_hours)) if row.regular_hours == row.regular_hours.to_integral() else format(row.regular_hours.normalize(), "f")))
        for row in AttendanceEntry.objects.for_company(company).filter(
            period=period, employee_id__in=employee_ids, work_date__in=work_dates
        )
    }
    return {
        "deltaOnly": True,
        "changes": [
            {"employeeId": employee_id, "day": work_date.day, "value": saved.get((employee_id, work_date), "")}
            for employee_id, work_date in requested
        ],
        "period": serialize_attendance_period(period, period_start=period.period_start, membership=membership),
        "summary": attendance_period_summary(company=company, period_start=period.period_start),
    }


def _overtime_delta(*, company, period, employee_ids: set[str], membership=None) -> dict[str, object]:
    rows = {
        str(row.employee_id): row
        for row in AttendanceOvertimeEntry.objects.for_company(company).filter(period=period, employee_id__in=employee_ids)
    }
    overtime: dict[str, dict[str, object]] = {}
    for employee_id in employee_ids:
        row = rows.get(employee_id)
        if row is None:
            overtime[employee_id] = {"hours": "0.00", "amount": "0.00", "saved": False}
            continue
        overtime[employee_id] = {
            "hours": str(row.hours), "amount": str(row.amount), "saved": True,
            "salaryStructureId": str(row.salary_structure_id), "policyCode": row.policy_code,
            "policyName": row.policy_name, "baseComponent": row.base_component_name,
            "baseAmount": str(row.base_amount), "divisor": str(row.divisor),
            "multiplier": str(row.multiplier), "rate": str(row.overtime_rate),
        }
    return {
        "deltaOnly": True,
        "period": serialize_attendance_period(period, period_start=period.period_start, membership=membership),
        "overtime": overtime,
        "summary": attendance_period_summary(company=company, period_start=period.period_start),
    }


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_ATTENDANCE_VIEW, PATCH=AccessPermission.INTERNAL_ATTENDANCE_EDIT)
def attendance_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            period_start = _request_period(request)
            page, page_size = _bounded_page(request)
            return JsonResponse(
                {
                    "ok": True,
                    **attendance_period_context(
                        company=request.company,
                        period_start=period_start,
                        membership=request.company_membership,
                        query=request.GET.get("q", ""),
                        branch=request.GET.get("branch", ""),
                        department=request.GET.get("department", ""),
                        page=page,
                        page_size=page_size,
                        include_summary=request.GET.get("summary", "1") != "0",
                    ),
                }
            )

        body = json_body(request)
        period_start = _request_period(request, body)
        raw_entries = body.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValidationError({"entries": "Entries must be a list."})
        period = save_attendance_entries(
            actor_membership=request.company_membership,
            period_start=period_start,
            entries=raw_entries,
            request=request,
        )
        return JsonResponse({"ok": True, **_attendance_delta(company=request.company, period=period, raw_entries=raw_entries, membership=request.company_membership)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(PATCH=AccessPermission.INTERNAL_ATTENDANCE_EDIT)
def overtime_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        raw_entries = body.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValidationError({"entries": "Entries must be a list."})
        period = save_overtime_entries(
            actor_membership=request.company_membership,
            period_start=period_start,
            entries=raw_entries,
            request=request,
        )
        employee_ids = {str(item.get("employee_id") or "") for item in raw_entries if item.get("employee_id")}
        return JsonResponse({"ok": True, **_overtime_delta(company=request.company, period=period, employee_ids=employee_ids, membership=request.company_membership)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=(AccessPermission.INTERNAL_ATTENDANCE_SUBMIT, AccessPermission.INTERNAL_ATTENDANCE_APPROVE))
def attendance_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        action = str(body.get("action") or "").strip().lower().replace("-", "_").replace(" ", "_")
        action = {
            "submit_for_review": "submit",
            "send_for_review": "submit",
            "lock_period": "lock",
            "return": "return_to_draft",
            "reject": "return_to_draft",
        }.get(action, action)
        required_permission = (
            AccessPermission.INTERNAL_ATTENDANCE_SUBMIT
            if action == "submit"
            else AccessPermission.INTERNAL_ATTENDANCE_APPROVE
            if action in {"approve", "lock", "return_to_draft"}
            else None
        )
        if required_permission is None:
            raise ValidationError({"action": "Unsupported attendance workflow action."})
        _require_action_permission(request, required_permission)
        period = transition_attendance_period(
            actor_membership=request.company_membership,
            period_start=period_start,
            action=action,
            reason=str(body.get("reason") or ""),
            request=request,
        )
        return JsonResponse({
            "ok": True, "deltaOnly": True,
            "period": serialize_attendance_period(period, period_start=period_start, membership=request.company_membership),
            "summary": attendance_period_summary(company=request.company, period_start=period_start),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=AccessPermission.INTERNAL_ATTENDANCE_EDIT)
def attendance_import_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        rows = body.get("rows", [])
        if not isinstance(rows, list):
            raise ValidationError({"rows": "Rows must be a list."})
        result = import_attendance_rows(
            actor_membership=request.company_membership,
            period_start=period_start,
            rows=rows,
            dry_run=bool(body.get("dry_run", False)),
            request=request,
        )
        payload = {"ok": True, "import": result}
        if not body.get("dry_run", False):
            period = attendance_period_context(
                company=request.company, period_start=period_start, membership=request.company_membership,
                page=1, page_size=25, include_summary=False,
            )["period"]
            payload.update({
                "deltaOnly": True, "period": period,
                "summary": attendance_period_summary(company=request.company, period_start=period_start),
            })
        return JsonResponse(payload)
    except Exception as exc:
        return handle_api_error(exc)
