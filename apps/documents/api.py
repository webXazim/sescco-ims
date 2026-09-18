from __future__ import annotations

import uuid
import hashlib
from pathlib import Path

import json
from datetime import date

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_company_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import branch_scope_ids, membership_has_permission, project_scope_ids, restrict_branch_snapshots, restrict_projects

from .models import BusinessDocument, DocumentType
from .selectors import document_page_context, documents_for_company, serialize_document
from .services import finalize_business_document
from .services.documents import SUPPLIER_TIMESHEET_ALIAS, SUPPLIER_TIMESHEET_VARIANT


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
    if request.content_type == "application/json":
        try:
            value = json.loads(request.body or b"{}")
        except json.JSONDecodeError as exc:
            raise ValidationError("Request body is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValidationError("JSON body must be an object.")
        return value
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        return request.POST.dict()
    raise ValidationError("Content-Type must be application/json or multipart/form-data.")


def _store_supplier_invoice_attachment(request: HttpRequest) -> dict[str, object] | None:
    uploaded = request.FILES.get("invoice_file")
    if uploaded is None:
        return None
    if uploaded.size <= 0 or uploaded.size > 12 * 1024 * 1024:
        raise ValidationError({"invoice_file": "Supplier invoice file must be between 1 byte and 12 MB."})
    original_name = Path(uploaded.name or "supplier-invoice").name
    head = uploaded.read(16)
    uploaded.seek(0)
    if head.startswith(b"%PDF-"):
        ext, content_type = ".pdf", "application/pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        ext, content_type = ".png", "image/png"
    elif head[:3] == b"\xff\xd8\xff":
        ext, content_type = ".jpg", "image/jpeg"
    else:
        raise ValidationError({"invoice_file": "Upload the supplier invoice as PDF, PNG, or JPEG."})
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    storage_key = default_storage.save(
        f"supplier-invoices/{request.company.id}/{uuid.uuid4().hex}{ext}",
        uploaded,
    )
    return {
        "storage_key": storage_key,
        "sha256": digest.hexdigest(),
        "content_type": content_type,
        "original_name": original_name,
        "size": uploaded.size,
    }


def _has_document_permission(membership, workspace: str, *, finalize: bool = False) -> bool:
    if workspace == "internal":
        specific = AccessPermission.INTERNAL_DOCUMENTS_FINALIZE if finalize else AccessPermission.INTERNAL_DOCUMENTS_VIEW
    elif workspace == "rental":
        specific = AccessPermission.RENTAL_DOCUMENTS_FINALIZE if finalize else AccessPermission.RENTAL_DOCUMENTS_VIEW
    else:
        return False
    shared = AccessPermission.SHARED_DOCUMENTS_FINALIZE if finalize else AccessPermission.SHARED_DOCUMENTS_VIEW
    return membership_has_permission(membership, specific) or membership_has_permission(membership, shared)


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
        requested_type = str(body.get("document_type") or "").strip()
        document_variant = str(body.get("document_variant") or "").strip()
        if requested_type == SUPPLIER_TIMESHEET_ALIAS:
            document_variant = SUPPLIER_TIMESHEET_VARIANT
        stored_attachment = None
        rental_types = {
            DocumentType.RENTAL_TIMESHEET, DocumentType.SUPPLIER_SETTLEMENT,
            DocumentType.SUPPLIER_INVOICE, DocumentType.SUPPLIER_PAYMENT_RECEIPT, SUPPLIER_TIMESHEET_ALIAS,
        }
        workspace_key = "rental" if requested_type in rental_types else "internal"
        if not _has_document_permission(request.company_membership, workspace_key, finalize=True):
            raise PermissionDenied("Your access profile cannot finalize documents for this workspace.")
        invoice = None
        if requested_type == DocumentType.SUPPLIER_INVOICE:
            raw_date = str(body.get("issue_date") or "")
            try:
                issue_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValidationError({"issue_date": "Enter a valid issue date."}) from exc
            stored_attachment = _store_supplier_invoice_attachment(request)
            if stored_attachment is None:
                raise ValidationError({"invoice_file": "Supplier invoice file is required."})
            invoice = {
                "invoice_number": body.get("invoice_number"),
                "issue_date": issue_date,
                "subtotal": body.get("subtotal"),
                "vat_amount": body.get("vat_amount", "0"),
                "total": body.get("total"),
                "attachment": stored_attachment,
            }
        document = finalize_business_document(
            actor_membership=request.company_membership,
            document_type=requested_type,
            source_id=body.get("source_id"),
            invoice=invoice,
            document_variant=document_variant,
            supplier_code=str(body.get("supplier_code") or ""),
            request=request,
        )
        if stored_attachment:
            actual_attachment = (((document.snapshot or {}).get("invoice") or {}).get("attachment") or {})
            if actual_attachment.get("storage_key") != stored_attachment.get("storage_key"):
                default_storage.delete(stored_attachment["storage_key"])
        return JsonResponse({"ok": True, "document": serialize_document(document, include_snapshot=True)}, status=201)
    except Exception as exc:
        try:
            if "stored_attachment" in locals() and stored_attachment and default_storage.exists(stored_attachment.get("storage_key", "")):
                default_storage.delete(stored_attachment["storage_key"])
        except Exception:
            pass
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def batch_supplier_settlement_statements_api(request: HttpRequest) -> JsonResponse:
    """Finalize one Supplier Settlement Statement per eligible supplier/project settlement."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        period_start = _period(str(body.get("period") or ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        from apps.rental_manpower.models import SupplierSettlement, RentalSettlementStatus

        final_statuses = [
            RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING,
            RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED,
        ]
        existing = BusinessDocument.objects.for_company(request.company).filter(
            document_type=DocumentType.SUPPLIER_SETTLEMENT,
            source_model="rental_manpower.suppliersettlement",
            source_id=OuterRef("pk"),
        )
        rows = restrict_projects(
            SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start, status__in=final_statuses),
            request.company_membership, field="project_id",
        ).annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("project_code", "supplier_code")
        project_id = str(body.get("project_id") or "").strip()
        if project_id:
            rows = rows.filter(project_id=project_id)
        source_ids = list(rows.values_list("pk", flat=True)[:201])
        if len(source_ids) > 200:
            raise ValidationError("Batch document creation is limited to 200 supplier settlements at a time.")
        created = []
        with transaction.atomic():
            for source_id in source_ids:
                document = finalize_business_document(
                    actor_membership=request.company_membership,
                    document_type=DocumentType.SUPPLIER_SETTLEMENT,
                    source_id=source_id, request=request,
                )
                created.append(serialize_document(document, include_snapshot=False))
        return JsonResponse({"ok": True, "created": len(created), "documents": created})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def batch_supplier_timesheet_statements_api(request: HttpRequest) -> JsonResponse:
    """Finalize one supplier-facing Timesheet Statement per supplier/project locked timesheet scope."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        period_start = _period(str(body.get("period") or ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetStatus

        existing = BusinessDocument.objects.for_company(request.company).filter(
            document_type=DocumentType.RENTAL_TIMESHEET,
            source_id=OuterRef("period_id"),
            entity_reference=OuterRef("supplier_code"),
            snapshot__document_variant=SUPPLIER_TIMESHEET_VARIANT,
        )
        rows = RentalTimesheetEntry.objects.for_company(request.company).filter(
            period__period_start=period_start,
            period__status=RentalTimesheetStatus.LOCKED,
        )
        allowed_projects = project_scope_ids(request.company_membership)
        if allowed_projects is not None:
            rows = rows.filter(period__project_id__in=allowed_projects) if allowed_projects else rows.none()
        supplier_code = str(body.get("supplier_code") or "").strip()
        project_id = str(body.get("project_id") or "").strip()
        if supplier_code:
            rows = rows.filter(supplier_code__iexact=supplier_code)
        if project_id:
            rows = rows.filter(period__project_id=project_id)
        rows = (
            rows.values("period_id", "supplier_code")
            .distinct()
            .annotate(_finalized=Exists(existing))
            .filter(_finalized=False)
            .order_by("supplier_code", "period_id")
        )
        source_rows = list(rows[:201])
        if len(source_rows) > 200:
            raise ValidationError("Batch document creation is limited to 200 supplier timesheets at a time.")
        created = []
        with transaction.atomic():
            for row in source_rows:
                document = finalize_business_document(
                    actor_membership=request.company_membership,
                    document_type=SUPPLIER_TIMESHEET_ALIAS,
                    document_variant=SUPPLIER_TIMESHEET_VARIANT,
                    source_id=row["period_id"],
                    supplier_code=row["supplier_code"],
                    request=request,
                )
                created.append(serialize_document(document, include_snapshot=False))
        return JsonResponse({"ok": True, "created": len(created), "documents": created})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_sources_api(request: HttpRequest) -> JsonResponse:
    """Paged, bounded eligible-source lookup used by the document creation drawer."""
    try:
        workspace = request.GET.get("workspace", "").strip()
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        membership = request.company_membership

        if workspace == "internal":
            if not _has_document_permission(membership, workspace, finalize=True):
                raise PermissionDenied("Your access profile cannot finalize Internal Company documents.")
            allowed_types = {DocumentType.SALARY_SLIP, DocumentType.INTERNAL_TIMESHEET, DocumentType.SALARY_PAYMENT_RECEIPT}
        elif workspace == "rental":
            if not _has_document_permission(membership, workspace, finalize=True):
                raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
            allowed_types = {DocumentType.RENTAL_TIMESHEET, SUPPLIER_TIMESHEET_ALIAS, DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE, DocumentType.SUPPLIER_PAYMENT_RECEIPT}
        else:
            raise ValidationError({"workspace": "Workspace must be internal or rental."})

        requested_type = request.GET.get("type", "").strip()
        if not requested_type:
            raise ValidationError({"type": "Choose a document type before searching source records."})
        if requested_type == SUPPLIER_TIMESHEET_ALIAS:
            document_type = SUPPLIER_TIMESHEET_ALIAS
            stored_document_type = DocumentType.RENTAL_TIMESHEET
            document_variant = SUPPLIER_TIMESHEET_VARIANT
        else:
            try:
                document_type = DocumentType(requested_type).value
            except ValueError as exc:
                raise ValidationError({"type": "Unsupported document type."}) from exc
            stored_document_type = document_type
            document_variant = ""
        if document_type not in allowed_types:
            raise PermissionDenied("This document type is not available in the selected workspace.")

        query = request.GET.get("q", "").strip()
        raw_employee_id = request.GET.get("employee_id", "").strip()
        scoped_employee_id = None
        if raw_employee_id:
            if workspace != "internal" or document_type not in {DocumentType.SALARY_SLIP, DocumentType.SALARY_PAYMENT_RECEIPT}:
                raise ValidationError({"employee_id": "Employee context is only valid for internal employee documents."})
            try:
                scoped_employee_id = uuid.UUID(raw_employee_id)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError({"employee_id": "Employee context must be a valid UUID."}) from exc

        requires_search = document_type in {DocumentType.SALARY_SLIP, DocumentType.SALARY_PAYMENT_RECEIPT} and scoped_employee_id is None
        try:
            page = max(1, int(request.GET.get("page", 1)))
            page_size = min(25, max(1, int(request.GET.get("page_size", 10))))
        except (TypeError, ValueError):
            page, page_size = 1, 10
        if requires_search and len(query) < 2:
            return JsonResponse({"ok": True, "sources": [], "meta": {"page": 1, "pageSize": page_size, "hasPrevious": False, "hasNext": False, "query": query, "type": document_type, "requiresSearch": True, "employeeScoped": False}})

        source_model_by_type = {
            DocumentType.SALARY_SLIP: "internal_payroll.payrollrunline",
            DocumentType.INTERNAL_TIMESHEET: "internal_payroll.attendanceperiod",
            DocumentType.SALARY_PAYMENT_RECEIPT: "internal_payroll.salarypaymentrow",
            DocumentType.RENTAL_TIMESHEET: "rental_manpower.rentaltimesheetperiod",
            SUPPLIER_TIMESHEET_ALIAS: "rental_manpower.rentaltimesheetperiod:supplier",
            DocumentType.SUPPLIER_SETTLEMENT: "rental_manpower.suppliersettlement",
            DocumentType.SUPPLIER_INVOICE: "rental_manpower.suppliersettlement",
            DocumentType.SUPPLIER_PAYMENT_RECEIPT: "rental_manpower.supplierpayment",
        }
        if document_type == SUPPLIER_TIMESHEET_ALIAS:
            existing = BusinessDocument.objects.for_company(request.company).filter(
                document_type=DocumentType.RENTAL_TIMESHEET,
                source_id=OuterRef("period_id"),
                entity_reference=OuterRef("supplier_code"),
                snapshot__document_variant=SUPPLIER_TIMESHEET_VARIANT,
            )
        else:
            existing = BusinessDocument.objects.for_company(request.company).filter(
                document_type=stored_document_type, source_model=source_model_by_type[document_type], source_id=OuterRef("pk")
            )
        start = (page - 1) * page_size
        stop = start + page_size + 1
        rows = []
        serialize = None

        if document_type == DocumentType.SALARY_SLIP:
            from apps.internal_payroll.models import PayrollRunLine, PayrollRunStatus
            final_runs = [PayrollRunStatus.APPROVED, PayrollRunStatus.PAYMENT_PROCESSING, PayrollRunStatus.PAID, PayrollRunStatus.CLOSED]
            qs = PayrollRunLine.objects.for_company(request.company).filter(run__period_start=period_start, run__status__in=final_runs)
            qs = restrict_branch_snapshots(qs, membership)
            if scoped_employee_id is not None:
                qs = qs.filter(employee_id=scoped_employee_id)
            else:
                qs = qs.filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(position__icontains=query))
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).select_related("run").order_by("employee_number")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name}", "status": row.run.get_status_display(), "amount": str(row.net), "employeeId": str(row.employee_id)}
        elif document_type == DocumentType.INTERNAL_TIMESHEET:
            from apps.internal_payroll.models import AttendancePeriod, AttendancePeriodStatus
            qs = AttendancePeriod.objects.for_company(request.company).filter(period_start=period_start, status=AttendancePeriodStatus.LOCKED)
            if membership.branch_scope_mode != "all":
                qs = qs.none()
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("pk")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"Internal Timesheet · {period_start:%B %Y}", "status": "Locked", "amount": None}
        elif document_type == DocumentType.SALARY_PAYMENT_RECEIPT:
            from apps.internal_payroll.models import SalaryPaymentRow, SalaryPaymentRowStatus
            qs = SalaryPaymentRow.objects.for_company(request.company).filter(batch__run__period_start=period_start, status=SalaryPaymentRowStatus.PAID)
            qs = restrict_branch_snapshots(qs, membership, field="run_line__branch_id_snapshot")
            if scoped_employee_id is not None:
                qs = qs.filter(employee_id=scoped_employee_id)
            else:
                qs = qs.filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(transaction_reference__icontains=query) | Q(batch__reference__icontains=query))
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).select_related("batch").order_by("employee_number", "paid_at")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"{row.employee_number} · {row.employee_name} · {row.transaction_reference or row.batch.reference}", "status": "Paid", "amount": str(row.amount), "employeeId": str(row.employee_id)}
        elif document_type == DocumentType.RENTAL_TIMESHEET:
            from apps.rental_manpower.models import RentalTimesheetPeriod, RentalTimesheetStatus
            qs = restrict_projects(
                RentalTimesheetPeriod.objects.for_company(request.company).filter(period_start=period_start, status=RentalTimesheetStatus.LOCKED),
                membership, field="project_id",
            )
            if query:
                qs = qs.filter(Q(project__code__icontains=query) | Q(project__name__icontains=query))
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).select_related("project").order_by("project__code")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"{row.project.code} · {row.project.name}", "status": "Locked", "amount": None}
        elif document_type == SUPPLIER_TIMESHEET_ALIAS:
            from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetStatus
            qs = RentalTimesheetEntry.objects.for_company(request.company).filter(
                period__period_start=period_start,
                period__status=RentalTimesheetStatus.LOCKED,
            )
            allowed_projects = project_scope_ids(membership)
            if allowed_projects is not None:
                qs = qs.filter(period__project_id__in=allowed_projects) if allowed_projects else qs.none()
            if query:
                qs = qs.filter(
                    Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query)
                    | Q(project_code__icontains=query) | Q(project_name__icontains=query)
                )
            qs = (
                qs.values("period_id", "supplier_code", "supplier_name", "project_code", "project_name")
                .distinct()
                .annotate(_finalized=Exists(existing))
                .filter(_finalized=False)
                .order_by("supplier_code", "project_code")
            )
            rows = qs[start:stop]
            serialize = lambda row: {
                "type": SUPPLIER_TIMESHEET_ALIAS,
                "storedType": DocumentType.RENTAL_TIMESHEET,
                "documentVariant": SUPPLIER_TIMESHEET_VARIANT,
                "sourceId": str(row["period_id"]),
                "label": f"{row['supplier_name']} · {row['project_name']}",
                "status": "Locked",
                "amount": None,
                "supplierCode": row["supplier_code"],
                "supplierName": row["supplier_name"],
                "projectCode": row["project_code"],
                "projectName": row["project_name"],
            }
        elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
            from apps.rental_manpower.models import SupplierSettlement, RentalSettlementStatus
            final_settlements = [RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED]
            if document_type == DocumentType.SUPPLIER_INVOICE:
                final_settlements = [RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID]
            qs = SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start, status__in=final_settlements)
            qs = restrict_projects(qs, membership, field="project_id")
            if query:
                qs = qs.filter(Q(settlement_number__icontains=query) | Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query) | Q(project_code__icontains=query) | Q(project_name__icontains=query))
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("project_code", "supplier_code")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"{row.settlement_number} · {row.supplier_name} · {row.project_name}", "status": row.get_status_display(), "amount": str(row.total_net)}
        elif document_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
            from apps.rental_manpower.models import SupplierPayment, SupplierPaymentStatus
            qs = SupplierPayment.objects.for_company(request.company).filter(allocations__settlement__period_start=period_start, status=SupplierPaymentStatus.PAID).distinct()
            allowed_projects = project_scope_ids(membership)
            if allowed_projects is not None:
                if not allowed_projects:
                    qs = qs.none()
                else:
                    from apps.rental_manpower.models import SupplierPaymentAllocation
                    outside = SupplierPaymentAllocation.objects.for_company(request.company).filter(payment_id=OuterRef("pk")).exclude(settlement__project_id__in=allowed_projects)
                    qs = qs.annotate(_outside_scope=Exists(outside)).filter(_outside_scope=False, allocations__settlement__project_id__in=allowed_projects).distinct()
            if query:
                qs = qs.filter(Q(payment_number__icontains=query) | Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query) | Q(transaction_reference__icontains=query))
            rows = qs.annotate(_finalized=Exists(existing)).filter(_finalized=False).order_by("payment_date", "payment_number")[start:stop]
            serialize = lambda row: {"type": document_type, "sourceId": str(row.id), "label": f"{row.payment_number} · {row.supplier_name}", "status": "Paid", "amount": str(row.amount)}

        window = list(rows)
        has_next = len(window) > page_size
        sources = [serialize(row) for row in window[:page_size]] if serialize else []
        return JsonResponse({
            "ok": True,
            "sources": sources,
            "meta": {"page": page, "pageSize": page_size, "hasPrevious": page > 1, "hasNext": has_next, "query": query, "type": document_type, "storedType": stored_document_type, "documentVariant": document_variant, "requiresSearch": requires_search, "employeeScoped": scoped_employee_id is not None},
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
