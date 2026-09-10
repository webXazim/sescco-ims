from __future__ import annotations

import uuid

import json
from datetime import date

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_company_required

from .models import BusinessDocument, DocumentType
from .selectors import documents_for_company, serialize_document
from .services import finalize_business_document


def _errors(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            errors = {key: [str(item) for item in values] for key, values in exc.message_dict.items()}
        else:
            errors = {"__all__": [str(item) for item in exc.messages]}
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    if isinstance(exc, ObjectDoesNotExist):
        return JsonResponse({"ok": False, "errors": {"__all__": ["Record not found."]}}, status=404)
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    if isinstance(exc, IntegrityError):
        return JsonResponse({"ok": False, "errors": {"__all__": ["The request conflicts with an existing final document."]}}, status=409)
    raise exc


def _body(request: HttpRequest) -> dict[str, object]:
    if request.content_type != "application/json":
        raise ValidationError("Content-Type must be application/json.")
    try:
        value = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Request body is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValidationError("JSON body must be an object.")
    return value


def _period(value: str):
    if not value:
        return None
    raw = value if len(value) != 7 else value + "-01"
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    return parsed.replace(day=1)


@require_http_methods(["GET", "POST"])
@api_company_required
def documents_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            rows = documents_for_company(
                company=request.company,
                membership=request.company_membership,
                workspace=request.GET.get("workspace", "").strip(),
                query=request.GET.get("q", ""),
                period_start=_period(request.GET.get("period", "")),
                document_type=request.GET.get("type", "").strip(),
            )[:500]
            return JsonResponse({"ok": True, "documents": [serialize_document(item) for item in rows]})
        body = _body(request)
        invoice = None
        if str(body.get("document_type") or "") == DocumentType.SUPPLIER_INVOICE:
            raw_date = str(body.get("issue_date") or "")
            try:
                issue_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValidationError({"issue_date": "Enter a valid issue date."}) from exc
            invoice = {
                "invoice_number": body.get("invoice_number"),
                "issue_date": issue_date,
                "subtotal": body.get("subtotal"),
                "vat_amount": body.get("vat_amount", "0"),
                "total": body.get("total"),
            }
        document = finalize_business_document(
            actor_membership=request.company_membership,
            document_type=str(body.get("document_type") or ""),
            source_id=body.get("source_id"),
            invoice=invoice,
            request=request,
        )
        return JsonResponse({"ok": True, "document": serialize_document(document, include_snapshot=True)}, status=201)
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_sources_api(request: HttpRequest) -> JsonResponse:
    try:
        workspace = request.GET.get("workspace", "").strip()
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        membership = request.company_membership
        from apps.accounts.permissions import membership_can_workspace
        from apps.accounts.roles import Workspace
        sources = []
        if workspace == "internal":
            if not membership_can_workspace(membership, Workspace.INTERNAL):
                raise PermissionDenied("Your role cannot access Internal Company documents.")
            from apps.internal_payroll.models import AttendancePeriod, AttendancePeriodStatus, PayrollRunLine, PayrollRunStatus, SalaryPaymentRow, SalaryPaymentRowStatus
            final_runs = [PayrollRunStatus.APPROVED, PayrollRunStatus.PAYMENT_PROCESSING, PayrollRunStatus.PAID, PayrollRunStatus.CLOSED]
            lines = PayrollRunLine.objects.for_company(request.company).filter(run__period_start=period_start, run__status__in=final_runs).select_related("run").order_by("employee_number")
            for row in lines:
                sources.append({"type": DocumentType.SALARY_SLIP, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name}", "status": row.run.get_status_display(), "amount": str(row.net)})
            attendance = AttendancePeriod.objects.for_company(request.company).filter(period_start=period_start, status=AttendancePeriodStatus.LOCKED).first()
            if attendance:
                sources.append({"type": DocumentType.INTERNAL_TIMESHEET, "sourceId": str(attendance.id), "label": f"Internal Timesheet · {period_start:%B %Y}", "status": "Locked", "amount": None})
            payments = SalaryPaymentRow.objects.for_company(request.company).filter(batch__run__period_start=period_start, status=SalaryPaymentRowStatus.PAID).select_related("batch").order_by("employee_number", "paid_at")
            for row in payments:
                sources.append({"type": DocumentType.SALARY_PAYMENT_RECEIPT, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name} · {row.transaction_reference or row.batch.reference}", "status": "Paid", "amount": str(row.amount)})
        elif workspace == "rental":
            if not membership_can_workspace(membership, Workspace.RENTAL):
                raise PermissionDenied("Your role cannot access Rental Manpower documents.")
            from apps.rental_manpower.models import RentalTimesheetPeriod, RentalTimesheetStatus, SupplierPayment, SupplierPaymentStatus, SupplierSettlement, RentalSettlementStatus
            for row in RentalTimesheetPeriod.objects.for_company(request.company).filter(period_start=period_start, status=RentalTimesheetStatus.LOCKED).select_related("project").order_by("project__code"):
                sources.append({"type": DocumentType.RENTAL_TIMESHEET, "sourceId": str(row.id), "label": f"{row.project.code} · {row.project.name}", "status": "Locked", "amount": None})
            final_settlements = [RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED]
            for row in SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start, status__in=final_settlements).order_by("project_code", "supplier_code"):
                base = {"sourceId": str(row.id), "label": f"{row.settlement_number} · {row.supplier_name} · {row.project_name}", "status": row.get_status_display(), "amount": str(row.total_net)}
                sources.append({"type": DocumentType.SUPPLIER_SETTLEMENT, **base})
                sources.append({"type": DocumentType.SUPPLIER_INVOICE, **base})
            payment_ids = SupplierPayment.objects.for_company(request.company).filter(allocations__settlement__period_start=period_start, status=SupplierPaymentStatus.PAID).distinct().values_list("id", flat=True)
            for row in SupplierPayment.objects.for_company(request.company).filter(id__in=payment_ids).order_by("payment_date", "payment_number"):
                sources.append({"type": DocumentType.SUPPLIER_PAYMENT_RECEIPT, "sourceId": str(row.id), "label": f"{row.payment_number} · {row.supplier_name}", "status": "Paid", "amount": str(row.amount)})
        else:
            raise ValidationError({"workspace": "Workspace must be internal or rental."})
        existing = set(BusinessDocument.objects.for_company(request.company).values_list("document_type", "source_id"))
        for item in sources:
            item["finalized"] = (item["type"], uuid.UUID(item["sourceId"])) in existing
        return JsonResponse({"ok": True, "sources": sources})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_detail_api(request: HttpRequest, document_id) -> JsonResponse:
    try:
        row = documents_for_company(company=request.company, membership=request.company_membership).get(pk=document_id)
        return JsonResponse({"ok": True, "document": serialize_document(row, include_snapshot=True)})
    except Exception as exc:
        return _errors(exc)
