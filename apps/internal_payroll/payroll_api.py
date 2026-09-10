from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import handle_api_error, json_body, parse_date, parse_optional_date
from apps.internal_payroll.selectors import payroll_period_context, serialize_payroll_policy
from apps.internal_payroll.services import (
    calculate_payroll_run,
    create_payroll_adjustment,
    reset_payroll_run,
    transition_payroll_adjustment,
    transition_payroll_run,
    update_payroll_adjustment,
    update_payroll_policy,
)


def _period_start(value: object) -> date:
    raw = str(value or "").strip()
    if len(raw) == 7:
        raw += "-01"
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    if parsed.day != 1:
        raise ValidationError({"period": "Period must identify a calendar month."})
    return parsed


def _request_period(request: HttpRequest, body: dict[str, object] | None = None) -> date:
    raw: object = request.GET.get("period", "")
    if not raw and body is not None:
        raw = body.get("period", "")
    if not raw:
        raise ValidationError({"period": "Period is required in YYYY-MM format."})
    return _period_start(raw)


def _decimal(value: object, field: str, *, optional: bool = False) -> Decimal | None:
    if optional and value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite number."}) from exc


@require_http_methods(["GET"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_api(request: HttpRequest) -> JsonResponse:
    try:
        period_start = _request_period(request)
        return JsonResponse(
            {
                "ok": True,
                **payroll_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_policy_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            from apps.internal_payroll.selectors import payroll_policy_for_company

            return JsonResponse({"ok": True, "policy": serialize_payroll_policy(payroll_policy_for_company(company=request.company))})
        body = json_body(request)
        policy = update_payroll_policy(
            actor_membership=request.company_membership,
            proration_method=str(body.get("proration_method") or ""),
            request=request,
        )
        return JsonResponse({"ok": True, "policy": serialize_payroll_policy(policy)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_calculate_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        calculate_payroll_run(
            actor_membership=request.company_membership,
            period_start=period_start,
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **payroll_period_context(
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
def payroll_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        action = str(body.get("action") or "")
        if action.strip().lower().replace("-", "_") == "reset":
            reset_payroll_run(
                actor_membership=request.company_membership,
                period_start=period_start,
                reason=str(body.get("note") or ""),
                request=request,
            )
        else:
            transition_payroll_run(
                actor_membership=request.company_membership,
                period_start=period_start,
                action=action,
                note=str(body.get("note") or ""),
                confirmed=body.get("confirmed") is True,
                request=request,
            )
        return JsonResponse(
            {
                "ok": True,
                **payroll_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_adjustments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse(
                {
                    "ok": True,
                    **payroll_period_context(
                        company=request.company,
                        period_start=period_start,
                        membership=request.company_membership,
                    ),
                }
            )
        body = json_body(request)
        period_start = _request_period(request, body)
        adjustment = create_payroll_adjustment(
            actor_membership=request.company_membership,
            employee_id=body.get("employee_id"),
            transaction_date=parse_date(body.get("transaction_date"), "transaction_date"),
            period_start=period_start,
            adjustment_type=str(body.get("adjustment_type") or ""),
            amount=_decimal(body.get("amount"), "amount") or Decimal("0"),
            reason=str(body.get("reason") or ""),
            reference=str(body.get("reference") or ""),
            recovery_plan=str(body.get("recovery_plan") or ""),
            installment_amount=_decimal(body.get("installment_amount"), "installment_amount", optional=True),
            recovery_start=parse_optional_date(body.get("recovery_start"), "recovery_start"),
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "adjustmentId": str(adjustment.pk),
                **payroll_period_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                ),
            },
            status=201,
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_adjustment_detail_api(request: HttpRequest, adjustment_id) -> JsonResponse:
    try:
        body = json_body(request)
        values: dict[str, object] = {}
        if "transaction_date" in body:
            values["transaction_date"] = parse_date(body.get("transaction_date"), "transaction_date")
        if "period" in body:
            values["period_start"] = _period_start(body.get("period"))
        if "adjustment_type" in body:
            values["adjustment_type"] = str(body.get("adjustment_type") or "")
        if "amount" in body:
            values["amount"] = _decimal(body.get("amount"), "amount") or Decimal("0")
        for field in ("reason", "reference", "recovery_plan"):
            if field in body:
                values[field] = str(body.get(field) or "")
        if "installment_amount" in body:
            values["installment_amount"] = _decimal(body.get("installment_amount"), "installment_amount", optional=True)
        if "recovery_start" in body:
            values["recovery_start"] = parse_optional_date(body.get("recovery_start"), "recovery_start")
        adjustment = update_payroll_adjustment(
            actor_membership=request.company_membership,
            adjustment_id=adjustment_id,
            values=values,
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **payroll_period_context(
                    company=request.company,
                    period_start=adjustment.period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def payroll_adjustment_workflow_api(request: HttpRequest, adjustment_id) -> JsonResponse:
    try:
        body = json_body(request)
        adjustment = transition_payroll_adjustment(
            actor_membership=request.company_membership,
            adjustment_id=adjustment_id,
            action=str(body.get("action") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                **payroll_period_context(
                    company=request.company,
                    period_start=adjustment.period_start,
                    membership=request.company_membership,
                ),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)
