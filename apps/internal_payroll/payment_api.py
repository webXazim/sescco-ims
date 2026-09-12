from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import handle_api_error, json_body
from apps.internal_payroll.models import BankExportTemplate
from apps.internal_payroll.selectors.payment import salary_payment_context, serialize_export_template, serialize_payment_profile, serialize_payment_settings
from apps.internal_payroll.services.payment import (
    archive_bank_export_template,
    cancel_salary_payment_batch,
    close_salary_payment_batch,
    create_bank_export_template,
    delete_unused_bank_export_template,
    delete_unused_employee_payment_profile,
    export_salary_payment_batch,
    import_salary_payment_results,
    prepare_salary_payment_batch,
    reopen_salary_payment_batch,
    restore_bank_export_template_archive,
    retry_salary_payment_row,
    start_salary_payment_batch,
    update_bank_export_template,
    update_company_salary_payment_settings,
    upsert_employee_payment_profile,
)


def _period_start(value: object) -> date:
    if not isinstance(value, str):
        raise ValidationError({"period": "Period must use YYYY-MM format."})
    try:
        year_text, month_text = value.split("-", 1)
        year, month = int(year_text), int(month_text)
        if month < 1 or month > 12:
            raise ValueError
        return date(year, month, 1)
    except (ValueError, TypeError) as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc


def _request_period(request: HttpRequest, body: dict[str, object] | None = None) -> date:
    value = body.get("period") if body is not None and "period" in body else request.GET.get("period")
    if not value:
        today = date.today()
        return date(today.year, today.month, 1)
    return _period_start(value)


@require_http_methods(["GET"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payments_api(request: HttpRequest) -> JsonResponse:
    try:
        period_start = _request_period(request)
        return JsonResponse({
            "ok": True,
            **salary_payment_context(
                company=request.company,
                period_start=period_start,
                membership=request.company_membership,
                bank_template_id=request.GET.get("bank_template_id") or None,
                wps_template_id=request.GET.get("wps_template_id") or None,
            ),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
def employee_payment_profile_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_employee_payment_profile(
                actor_membership=request.company_membership, employee_id=employee_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedPaymentProfileId": deleted_id})
        allowed = {
            "destination_type", "account_holder_name", "bank_name", "bank_code",
            "iban", "salary_card_number", "wps_enabled", "is_active", "mark_verified",
        }
        values = {key: value for key, value in body.items() if key in allowed}
        profile = upsert_employee_payment_profile(
            actor_membership=request.company_membership,
            employee_id=employee_id,
            values=values,
            request=request,
        )
        return JsonResponse({"ok": True, "profile": serialize_payment_profile(profile)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payment_settings_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        row = update_company_salary_payment_settings(actor_membership=request.company_membership, values=body, request=request)
        return JsonResponse({"ok": True, "settings": serialize_payment_settings(row)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def bank_export_templates_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            rows = BankExportTemplate.objects.for_company(request.company).order_by("channel", "name")
            return JsonResponse({"ok": True, "templates": [serialize_export_template(item) for item in rows]})
        body = json_body(request)
        columns = body.get("columns")
        if not isinstance(columns, list):
            raise ValidationError({"columns": "Columns must be a JSON array."})
        headers = body.get("headers", [])
        result_columns = body.get("result_columns", {})
        if not isinstance(headers, list):
            raise ValidationError({"headers": "Headers must be a JSON array."})
        if not isinstance(result_columns, dict):
            raise ValidationError({"result_columns": "Result columns must be a JSON object."})
        template = create_bank_export_template(
            actor_membership=request.company_membership,
            code=str(body.get("code") or ""),
            name=str(body.get("name") or ""),
            channel=str(body.get("channel") or "bank_csv"),
            delimiter=str(body.get("delimiter") or "comma"),
            encoding=str(body.get("encoding") or "utf-8"),
            include_header=body.get("include_header") is not False,
            columns=[str(item) for item in columns],
            headers=[str(item) for item in headers],
            result_columns={str(key): str(value) for key, value in result_columns.items()},
            is_active=body.get("is_active") is not False,
            request=request,
        )
        return JsonResponse({"ok": True, "template": serialize_export_template(template)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
def bank_export_template_detail_api(request: HttpRequest, template_id) -> JsonResponse:
    try:
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_bank_export_template(
                actor_membership=request.company_membership, template_id=template_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedTemplateId": deleted_id})
        values: dict[str, object] = {}
        mapping = {
            "code": "code",
            "name": "name",
            "channel": "channel",
            "delimiter": "delimiter",
            "encoding": "encoding",
            "include_header": "include_header",
            "columns": "columns",
            "headers": "headers",
            "result_columns": "result_columns",
            "is_active": "is_active",
        }
        for source, target in mapping.items():
            if source in body:
                values[target] = body[source]
        if "columns" in values and not isinstance(values["columns"], list):
            raise ValidationError({"columns": "Columns must be a JSON array."})
        if "headers" in values and not isinstance(values["headers"], list):
            raise ValidationError({"headers": "Headers must be a JSON array."})
        if "result_columns" in values and not isinstance(values["result_columns"], dict):
            raise ValidationError({"result_columns": "Result columns must be a JSON object."})
        template = update_bank_export_template(actor_membership=request.company_membership, template_id=template_id, values=values, request=request)
        return JsonResponse({"ok": True, "template": serialize_export_template(template)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def bank_export_template_lifecycle_api(request: HttpRequest, template_id) -> JsonResponse:
    try:
        body = json_body(request); action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            template = archive_bank_export_template(actor_membership=request.company_membership, template_id=template_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            template = restore_bank_export_template_archive(actor_membership=request.company_membership, template_id=template_id, reason=str(body.get("reason", "")), request=request)
        else:
            raise ValidationError({"action": "Export-template lifecycle action must be archive or restore."})
        return JsonResponse({"ok": True, "template": serialize_export_template(template)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def prepare_salary_payment_batch_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        batch = prepare_salary_payment_batch(
            actor_membership=request.company_membership,
            period_start=period_start,
            channel=str(body.get("channel") or ""),
            template_id=body.get("template_id"),
            note=str(body.get("note") or ""),
            request=request,
        )
        return JsonResponse({"ok": True, "batchId": str(batch.pk), **salary_payment_context(company=request.company, period_start=period_start, membership=request.company_membership)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payment_batch_export_api(request: HttpRequest, batch_id) -> HttpResponse:
    try:
        _body = json_body(request)
        batch, data, filename, content_type = export_salary_payment_batch(actor_membership=request.company_membership, batch_id=batch_id, request=request)
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Payroll-Batch"] = batch.reference
        response["X-Content-SHA256"] = batch.last_export_sha256
        return response
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payment_batch_workflow_api(request: HttpRequest, batch_id) -> JsonResponse:
    try:
        body = json_body(request)
        action = str(body.get("action") or "").strip().lower().replace("-", "_")
        if action == "start":
            batch = start_salary_payment_batch(actor_membership=request.company_membership, batch_id=batch_id, request=request)
        elif action == "cancel":
            batch = cancel_salary_payment_batch(actor_membership=request.company_membership, batch_id=batch_id, reason=str(body.get("reason") or ""), request=request)
        elif action == "close":
            batch = close_salary_payment_batch(actor_membership=request.company_membership, batch_id=batch_id, request=request)
        elif action == "reopen":
            batch = reopen_salary_payment_batch(actor_membership=request.company_membership, batch_id=batch_id, reason=str(body.get("reason") or ""), request=request)
        else:
            raise ValidationError({"action": "Unsupported salary payment batch action."})
        return JsonResponse({"ok": True, **salary_payment_context(company=request.company, period_start=batch.run.period_start, membership=request.company_membership)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payment_results_api(request: HttpRequest, batch_id) -> JsonResponse:
    try:
        body = json_body(request)
        content = body.get("content")
        if not isinstance(content, str):
            raise ValidationError({"content": "Bank result file content is required."})
        batch, result, errors = import_salary_payment_results(
            actor_membership=request.company_membership,
            batch_id=batch_id,
            file_name=str(body.get("file_name") or "bank-results.csv"),
            content=content,
            request=request,
        )
        return JsonResponse({
            "ok": True,
            "resultImportId": str(result.pk),
            "import": {
                "fileName": result.file_name,
                "updatedRows": result.updated_rows,
                "errorCount": result.error_count,
            },
            "errors": errors,
            **salary_payment_context(company=request.company, period_start=batch.run.period_start, membership=request.company_membership),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def salary_payment_row_retry_api(request: HttpRequest, row_id) -> JsonResponse:
    try:
        _body = json_body(request)
        row = retry_salary_payment_row(actor_membership=request.company_membership, row_id=row_id, request=request)
        return JsonResponse({"ok": True, **salary_payment_context(company=request.company, period_start=row.batch.run.period_start, membership=request.company_membership)})
    except Exception as exc:
        return handle_api_error(exc)
