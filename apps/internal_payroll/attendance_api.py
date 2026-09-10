from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import handle_api_error, json_body
from apps.internal_payroll.selectors import attendance_period_context
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


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def attendance_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse(
                {
                    "ok": True,
                    **attendance_period_context(
                        company=request.company,
                        period_start=period_start,
                        membership=request.company_membership,
                    ),
                }
            )

        body = json_body(request)
        period_start = _request_period(request, body)
        raw_entries = body.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValidationError({"entries": "Entries must be a list."})
        save_attendance_entries(
            actor_membership=request.company_membership,
            period_start=period_start,
            entries=raw_entries,
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **attendance_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def overtime_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        raw_entries = body.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValidationError({"entries": "Entries must be a list."})
        save_overtime_entries(
            actor_membership=request.company_membership,
            period_start=period_start,
            entries=raw_entries,
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **attendance_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def attendance_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        transition_attendance_period(
            actor_membership=request.company_membership,
            period_start=period_start,
            action=str(body.get("action") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **attendance_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
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
            payload.update(
                attendance_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                )
            )
        return JsonResponse(payload)
    except Exception as exc:
        return handle_api_error(exc)
