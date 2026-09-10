from __future__ import annotations

import csv
from datetime import date
from io import StringIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability, Workspace

from .management import available_report_periods, build_report, management_context


def _period(raw: str) -> date:
    value = raw.strip()
    if len(value) == 7:
        value += "-01"
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    if result.day != 1:
        raise ValidationError({"period": "Period must identify a calendar month."})
    return result


def _error(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            errors = {k: [str(v) for v in values] for k, values in exc.message_dict.items()}
        else:
            errors = {"__all__": [str(v) for v in exc.messages]}
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    if isinstance(exc, ValueError):
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=400)
    raise exc


@require_GET
@api_workspace_required(Workspace.MANAGEMENT)
def management_api(request: HttpRequest) -> JsonResponse:
    try:
        period = _period(request.GET.get("period", ""))
        payload = management_context(company=request.company, period_start=period)
        if not membership_has_capability(request.company_membership, Capability.VIEW_AUDIT):
            payload["audit"] = []
        return JsonResponse({"ok": True, "management": payload})
    except Exception as exc:
        return _error(exc)


def _report_payload(request: HttpRequest) -> dict[str, object]:
    if not request.user.is_authenticated:
        raise PermissionError("Authentication is required.")
    membership = getattr(request, "company_membership", None)
    if membership is None:
        raise PermissionDenied("No active company access is assigned to this account.")
    workspace = request.GET.get("workspace", "").strip()
    try:
        workspace_enum = Workspace(workspace)
    except ValueError as exc:
        raise ValidationError({"workspace": "Unknown workspace."}) from exc
    from apps.accounts.permissions import membership_can_workspace
    if not membership_can_workspace(membership, workspace_enum):
        raise PermissionDenied("Your role cannot access this workspace.")
    period = _period(request.GET.get("period", ""))
    report = build_report(
        company=request.company,
        report_type=request.GET.get("type", ""),
        period_start=period,
        workspace=workspace,
    )
    periods = [{"key": item.strftime("%Y-%m"), "label": item.strftime("%B %Y")} for item in available_report_periods(request.company)]
    return {"ok": True, "report": report, "periods": periods}


def _csv_cell(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


@require_GET
def reports_api(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Authentication is required."]}}, status=401)
    try:
        return JsonResponse(_report_payload(request))
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except Exception as exc:
        return _error(exc)


@require_GET
def report_export_api(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Authentication is required."]}}, status=401)
    try:
        payload = _report_payload(request)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except Exception as exc:
        return _error(exc)
    report = payload["report"]
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([_csv_cell(value) for value in report["columns"]])
    writer.writerows([[_csv_cell(value) for value in row] for row in report["rows"]])
    filename = f"{request.GET.get('type','report')}-{request.GET.get('period','period')}.csv"
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'"
    return response
