from __future__ import annotations

import uuid

import json
from datetime import date

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_company_required

from .models import BusinessDocument, DocumentType
from .selectors import document_page_context, documents_for_company, serialize_document
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
            payload = document_page_context(
                company=request.company,
                membership=request.company_membership,
                workspace=request.GET.get("workspace", "").strip(),
                query=request.GET.get("q", ""),
                period_start=_period(request.GET.get("period", "")),
                document_type=request.GET.get("type", "").strip(),
                entity_reference=request.GET.get("entity_reference", "").strip(),
                page=request.GET.get("page", 1),
                page_size=request.GET.get("page_size", 50),
            )
            return JsonResponse({"ok": True, **payload})
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
    """Return a bounded searchable set of eligible source records for one document type.

    Final-document creation must never hydrate the full employee/worker/payment/settlement master.
    The browser selects a document type first, then searches a maximum of 25 company-scoped sources.
    """
    try:
        workspace = request.GET.get("workspace", "").strip()
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        membership = request.company_membership
        from apps.accounts.permissions import membership_can_workspace
        from apps.accounts.roles import Workspace

        if workspace == "internal":
            if not membership_can_workspace(membership, Workspace.INTERNAL):
                raise PermissionDenied("Your role cannot access Internal Company documents.")
            allowed_types = {
                DocumentType.SALARY_SLIP,
                DocumentType.INTERNAL_TIMESHEET,
                DocumentType.SALARY_PAYMENT_RECEIPT,
            }
        elif workspace == "rental":
            if not membership_can_workspace(membership, Workspace.RENTAL):
                raise PermissionDenied("Your role cannot access Rental Manpower documents.")
            allowed_types = {
                DocumentType.RENTAL_TIMESHEET,
                DocumentType.SUPPLIER_SETTLEMENT,
                DocumentType.SUPPLIER_INVOICE,
                DocumentType.SUPPLIER_PAYMENT_RECEIPT,
            }
        else:
            raise ValidationError({"workspace": "Workspace must be internal or rental."})

        requested_type = request.GET.get("type", "").strip()
        if not requested_type:
            raise ValidationError({"type": "Choose a document type before searching source records."})
        try:
            document_type = DocumentType(requested_type).value
        except ValueError as exc:
            raise ValidationError({"type": "Unsupported document type."}) from exc
        if document_type not in allowed_types:
            raise PermissionDenied("This document type is not available in the selected workspace.")

        query = request.GET.get("q", "").strip()
        try:
            limit = min(25, max(1, int(request.GET.get("limit", 25))))
        except (TypeError, ValueError):
            limit = 25

        source_model_by_type = {
            DocumentType.SALARY_SLIP: "internal_payroll.payrollrunline",
            DocumentType.INTERNAL_TIMESHEET: "internal_payroll.attendanceperiod",
            DocumentType.SALARY_PAYMENT_RECEIPT: "internal_payroll.salarypaymentrow",
            DocumentType.RENTAL_TIMESHEET: "rental_manpower.rentaltimesheetperiod",
            DocumentType.SUPPLIER_SETTLEMENT: "rental_manpower.suppliersettlement",
            DocumentType.SUPPLIER_INVOICE: "rental_manpower.suppliersettlement",
            DocumentType.SUPPLIER_PAYMENT_RECEIPT: "rental_manpower.supplierpayment",
        }
        existing = BusinessDocument.objects.for_company(request.company).filter(
            document_type=document_type,
            source_model=source_model_by_type[document_type],
            source_id=OuterRef("pk"),
        )
        sources: list[dict[str, object]] = []

        if document_type == DocumentType.SALARY_SLIP:
            if len(query) >= 2:
                from apps.internal_payroll.models import PayrollRunLine, PayrollRunStatus
                final_runs = [PayrollRunStatus.APPROVED, PayrollRunStatus.PAYMENT_PROCESSING, PayrollRunStatus.PAID, PayrollRunStatus.CLOSED]
                rows = (
                    PayrollRunLine.objects.for_company(request.company)
                    .filter(run__period_start=period_start, run__status__in=final_runs)
                    .filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(position__icontains=query))
                    .annotate(_finalized=Exists(existing))
                    .filter(_finalized=False)
                    .select_related("run")
                    .order_by("employee_number")[:limit]
                )
                for row in rows:
                    sources.append({"type": document_type, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name}", "status": row.run.get_status_display(), "amount": str(row.net)})
        elif document_type == DocumentType.INTERNAL_TIMESHEET:
            from apps.internal_payroll.models import AttendancePeriod, AttendancePeriodStatus
            rows = (
                AttendancePeriod.objects.for_company(request.company)
                .filter(period_start=period_start, status=AttendancePeriodStatus.LOCKED)
                .annotate(_finalized=Exists(existing))
                .filter(_finalized=False)[:1]
            )
            for row in rows:
                sources.append({"type": document_type, "sourceId": str(row.id), "label": f"Internal Timesheet · {period_start:%B %Y}", "status": "Locked", "amount": None})
        elif document_type == DocumentType.SALARY_PAYMENT_RECEIPT:
            if len(query) >= 2:
                from apps.internal_payroll.models import SalaryPaymentRow, SalaryPaymentRowStatus
                rows = (
                    SalaryPaymentRow.objects.for_company(request.company)
                    .filter(batch__run__period_start=period_start, status=SalaryPaymentRowStatus.PAID)
                    .filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(transaction_reference__icontains=query) | Q(batch__reference__icontains=query))
                    .annotate(_finalized=Exists(existing))
                    .filter(_finalized=False)
                    .select_related("batch")
                    .order_by("employee_number", "paid_at")[:limit]
                )
                for row in rows:
                    sources.append({"type": document_type, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name} · {row.transaction_reference or row.batch.reference}", "status": "Paid", "amount": str(row.amount)})
        elif document_type == DocumentType.RENTAL_TIMESHEET:
            from apps.rental_manpower.models import RentalTimesheetPeriod, RentalTimesheetStatus
            rows = RentalTimesheetPeriod.objects.for_company(request.company).filter(period_start=period_start, status=RentalTimesheetStatus.LOCKED)
            if query:
                rows = rows.filter(Q(project__code__icontains=query) | Q(project__name__icontains=query))
            rows = rows.annotate(_finalized=Exists(existing)).filter(_finalized=False).select_related("project").order_by("project__code")[:limit]
            for row in rows:
                sources.append({"type": document_type, "sourceId": str(row.id), "label": f"{row.project.code} · {row.project.name}", "status": "Locked", "amount": None})
        elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
            from apps.rental_manpower.models import SupplierSettlement, RentalSettlementStatus
            final_settlements = [RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED]
            rows = SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start, status__in=final_settlements)
            if query:
                rows = rows.filter(Q(settlement_number__icontains=query) | Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query) | Q(project_code__icontains=query) | Q(project_name__icontains=query))
            rows = rows.annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("project_code", "supplier_code")[:limit]
            for row in rows:
                sources.append({"type": document_type, "sourceId": str(row.id), "label": f"{row.settlement_number} · {row.supplier_name} · {row.project_name}", "status": row.get_status_display(), "amount": str(row.total_net)})
        elif document_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
            from apps.rental_manpower.models import SupplierPayment, SupplierPaymentStatus
            rows = SupplierPayment.objects.for_company(request.company).filter(allocations__settlement__period_start=period_start, status=SupplierPaymentStatus.PAID).distinct()
            if query:
                rows = rows.filter(Q(payment_number__icontains=query) | Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query) | Q(transaction_reference__icontains=query))
            rows = rows.annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("payment_date", "payment_number")[:limit]
            for row in rows:
                sources.append({"type": document_type, "sourceId": str(row.id), "label": f"{row.payment_number} · {row.supplier_name}", "status": "Paid", "amount": str(row.amount)})

        return JsonResponse({
            "ok": True,
            "sources": sources,
            "meta": {"limit": limit, "query": query, "type": document_type, "requiresSearch": document_type in {DocumentType.SALARY_SLIP, DocumentType.SALARY_PAYMENT_RECEIPT}},
        })
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
