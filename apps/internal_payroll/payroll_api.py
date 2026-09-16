from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.api_permissions import api_method_access_required, api_workspace_required
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.roles import Workspace
from apps.internal_payroll.api_utils import handle_api_error, json_body, parse_date, parse_optional_date
from apps.internal_payroll.models import PayrollAdjustment
from apps.internal_payroll.selectors import payroll_period_context, serialize_payroll_adjustment, serialize_payroll_policy
from apps.internal_payroll.selectors.payroll import payroll_adjustment_page_context, payroll_run_page_context
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


def _require_action_permission(request: HttpRequest, permission: AccessPermission) -> None:
    if not membership_has_permission(request.company_membership, permission):
        raise PermissionDenied("Your access profile does not allow this workflow action.")


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
@api_method_access_required(GET=AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW)
def payroll_api(request: HttpRequest) -> JsonResponse:
    try:
        period_start = _request_period(request)
        if str(request.GET.get("surface") or "").strip().lower() == "run":
            context = payroll_run_page_context(
                company=request.company,
                period_start=period_start,
                membership=request.company_membership,
                page=request.GET.get("page", 1),
                page_size=request.GET.get("page_size", 50),
                search=str(request.GET.get("search") or ""),
                branch=str(request.GET.get("branch") or "All branches"),
                department=str(request.GET.get("department") or "All departments"),
                readiness=str(request.GET.get("readiness") or "All"),
            )
        else:
            context = payroll_period_context(
                company=request.company,
                period_start=period_start,
                membership=request.company_membership,
            )
        return JsonResponse({"ok": True, **context})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW, PATCH=AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE)
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
@api_method_access_required(POST=AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE)
def payroll_calculate_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        calculate_payroll_run(
            actor_membership=request.company_membership,
            period_start=period_start,
            request=request,
        )
        context = (
            payroll_run_page_context(
                company=request.company, period_start=period_start, membership=request.company_membership,
                page=body.get("page", 1), page_size=body.get("page_size", 50),
                search=str(body.get("search") or ""), branch=str(body.get("branch") or "All branches"),
                department=str(body.get("department") or "All departments"), readiness=str(body.get("readiness") or "All"),
            )
            if str(body.get("surface") or "").strip().lower() == "run"
            else payroll_period_context(company=request.company, period_start=period_start, membership=request.company_membership)
        )
        return JsonResponse({"ok": True, **context})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=(AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE, AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW, AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE))
def payroll_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        period_start = _request_period(request, body)
        action = str(body.get("action") or "")
        normalized_action = action.strip().lower().replace("-", "_").replace(" ", "_")
        normalized_action = {
            "submit": "submit_review",
            "submit_for_review": "submit_review",
            "mark_reviewed": "review",
            "review_complete": "review",
            "return": "return_for_changes",
            "return_to_draft": "return_for_changes",
        }.get(normalized_action, normalized_action)
        if normalized_action == "reset":
            _require_action_permission(request, AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE)
            reset_payroll_run(
                actor_membership=request.company_membership,
                period_start=period_start,
                reason=str(body.get("note") or ""),
                request=request,
            )
        else:
            required_permission = {
                "submit_review": AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE,
                "review": AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW,
                "return_for_changes": AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW,
                "approve": AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE,
            }.get(normalized_action)
            if required_permission is None:
                raise ValidationError({"action": "Unsupported payroll workflow action."})
            _require_action_permission(request, required_permission)
            transition_payroll_run(
                actor_membership=request.company_membership,
                period_start=period_start,
                action=normalized_action,
                note=str(body.get("note") or ""),
                confirmed=body.get("confirmed") is True,
                request=request,
            )
        context = (
            payroll_run_page_context(
                company=request.company, period_start=period_start, membership=request.company_membership,
                page=body.get("page", 1), page_size=body.get("page_size", 50),
                search=str(body.get("search") or ""), branch=str(body.get("branch") or "All branches"),
                department=str(body.get("department") or "All departments"), readiness=str(body.get("readiness") or "All"),
            )
            if str(body.get("surface") or "").strip().lower() == "run"
            else payroll_period_context(company=request.company, period_start=period_start, membership=request.company_membership)
        )
        return JsonResponse({"ok": True, **context})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(GET=AccessPermission.INTERNAL_ADJUSTMENTS_VIEW, POST=AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE)
def payroll_adjustments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse(
                {
                    "ok": True,
                    **payroll_adjustment_page_context(
                        company=request.company,
                        period_start=period_start,
                        page=request.GET.get("page", 1),
                        page_size=request.GET.get("page_size", 50),
                        search=str(request.GET.get("search") or ""),
                        adjustment_type=str(request.GET.get("type") or "All"),
                        status=str(request.GET.get("status") or "All"),
                        view=str(request.GET.get("view") or "register"),
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
        adjustment = PayrollAdjustment.objects.for_company(request.company).select_related("employee", "submitted_by", "approved_by").get(pk=adjustment.pk)
        return JsonResponse(
            {
                "ok": True,
                "adjustmentId": str(adjustment.pk),
                "period": f"{period_start:%Y-%m}",
                "adjustment": serialize_payroll_adjustment(adjustment),
            },
            status=201,
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(PATCH=AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE)
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
        adjustment = PayrollAdjustment.objects.for_company(request.company).select_related("employee", "submitted_by", "approved_by").get(pk=adjustment.pk)
        return JsonResponse(
            {
                "ok": True,
                "period": f"{adjustment.period_start:%Y-%m}",
                "adjustment": serialize_payroll_adjustment(adjustment),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
@api_method_access_required(POST=(AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE, AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE))
def payroll_adjustment_workflow_api(request: HttpRequest, adjustment_id) -> JsonResponse:
    try:
        body = json_body(request)
        action = str(body.get("action") or "").strip().lower().replace("-", "_").replace(" ", "_")
        action = {"submit_for_review": "submit", "return": "return_to_draft", "reject": "return_to_draft"}.get(action, action)
        required_permission = (
            AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE
            if action == "submit"
            else AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE
            if action in {"approve", "return_to_draft"}
            else None
        )
        if required_permission is None:
            raise ValidationError({"action": "Unsupported payroll adjustment workflow action."})
        _require_action_permission(request, required_permission)
        adjustment = transition_payroll_adjustment(
            actor_membership=request.company_membership,
            adjustment_id=adjustment_id,
            action=action,
            reason=str(body.get("reason") or ""),
            request=request,
        )
        adjustment = PayrollAdjustment.objects.for_company(request.company).select_related("employee", "submitted_by", "approved_by").get(pk=adjustment.pk)
        return JsonResponse(
            {
                "ok": True,
                "period": f"{adjustment.period_start:%Y-%m}",
                "adjustment": serialize_payroll_adjustment(adjustment),
            }
        )
    except Exception as exc:
        return handle_api_error(exc)
