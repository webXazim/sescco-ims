from __future__ import annotations

import uuid
import hashlib
from pathlib import Path

import json
from datetime import date
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.utils.html import escape

from apps.accounts.api_permissions import api_company_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import branch_scope_ids, membership_has_permission, project_scope_ids, restrict_branch_snapshots, restrict_projects
from apps.core.models import AuditArea, AuditEvent
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number

from .models import BusinessDocument, DocumentType
from .selectors import document_page_context, document_preview_fragment, documents_for_company, serialize_document
from .services import finalize_business_document, verify_document_snapshot
from .services.documents import SUPPLIER_TIMESHEET_ALIAS, SUPPLIER_TIMESHEET_VARIANT
from .services.type_first_generator import (
    TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE,
    eligible_projects,
    eligible_sources,
    eligible_suppliers,
    normalize_type_first_document_type,
    review_type_first_source,
    selector_page,
    type_first_generator_catalog,
    type_first_meta,
)
from .delivery import (
    DELIVERY_SHARE_REISSUED_ACTION, DELIVERY_SHARE_REVOKED_ACTION,
    SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE, SUPPLIER_DELIVERY_CONTRACT_VERSION,
    delivery_share_generation, delivery_share_is_revoked, delivery_share_revoked_event,
    delivery_share_expires_at, delivery_share_is_expired,
    make_delivery_share_token, delivery_share_ttl_seconds,
    prefer_v3_supplier_timesheets, supplier_delivery_document_label, supplier_delivery_document_role,
    supplier_delivery_filename, supplier_delivery_is_primary, supplier_delivery_manifest_entry,
)


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


def _type_first_period(request: HttpRequest, body: dict[str, object] | None = None):
    value = (body or {}).get("period") if body is not None else request.GET.get("period", "")
    period_start = _period(str(value or ""))
    if period_start is None:
        raise ValidationError({"period": "Period is required."})
    return period_start


def _type_first_selector_meta(*, page: int, page_size: int, has_next: bool, query: str, document_type: str) -> dict[str, object]:
    return {
        "page": page,
        "pageSize": page_size,
        "maxPageSize": TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE,
        "hasPrevious": page > 1,
        "hasNext": bool(has_next),
        "query": query,
        "documentType": document_type,
    }


@require_http_methods(["GET"])
@api_company_required
def document_generator_types_api(request: HttpRequest) -> JsonResponse:
    """Return the lightweight purpose-first Rental document catalog.

    This endpoint deliberately performs no Payroll/Rental source discovery. Opening the future
    generator therefore does not scan suppliers, projects, settlements or timesheet rows.
    """
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        return JsonResponse({
            "ok": True,
            "types": type_first_generator_catalog(),
            "selectorMaxPageSize": TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE,
            "bulk": {
                "generationPlanEndpoint": reverse("documents:document-generation-plan-api"),
                "generationExecuteEndpoint": reverse("documents:document-generation-execute-api"),
            },
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_generator_suppliers_api(request: HttpRequest) -> JsonResponse:
    """Bounded eligible suppliers for one already-selected document purpose and month."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        document_type = normalize_type_first_document_type(request.GET.get("type", ""))
        period_start = _type_first_period(request)
        query = request.GET.get("q", "").strip()
        page, page_size = selector_page(request.GET.get("page"), request.GET.get("page_size"))
        payload = eligible_suppliers(
            company=request.company, membership=request.company_membership, document_type=document_type,
            period_start=period_start, query=query, page=page, page_size=page_size,
        )
        return JsonResponse({
            "ok": True,
            "suppliers": payload["results"],
            "period": period_start.strftime("%Y-%m"),
            "meta": _type_first_selector_meta(page=page, page_size=page_size, has_next=payload["hasNext"], query=query, document_type=document_type),
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_generator_projects_api(request: HttpRequest) -> JsonResponse:
    """Bounded projects that are actually eligible for the chosen supplier/type/month."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        document_type = normalize_type_first_document_type(request.GET.get("type", ""))
        period_start = _type_first_period(request)
        supplier_code = request.GET.get("supplier_code", "").strip()
        query = request.GET.get("q", "").strip()
        page, page_size = selector_page(request.GET.get("page"), request.GET.get("page_size"))
        payload = eligible_projects(
            company=request.company, membership=request.company_membership, document_type=document_type,
            period_start=period_start, supplier_code=supplier_code, query=query, page=page, page_size=page_size,
        )
        return JsonResponse({
            "ok": True,
            "projects": payload["results"],
            "supplierCode": supplier_code.upper(),
            "period": period_start.strftime("%Y-%m"),
            "meta": _type_first_selector_meta(page=page, page_size=page_size, has_next=payload["hasNext"], query=query, document_type=document_type),
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_generator_sources_api(request: HttpRequest) -> JsonResponse:
    """Return only the final source records matching the selected type/supplier/project/month."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        document_type = normalize_type_first_document_type(request.GET.get("type", ""))
        period_start = _type_first_period(request)
        supplier_code = request.GET.get("supplier_code", "").strip()
        project_id = request.GET.get("project_id", "").strip()
        query = request.GET.get("q", "").strip()
        page, page_size = selector_page(request.GET.get("page"), request.GET.get("page_size"))
        payload = eligible_sources(
            company=request.company, membership=request.company_membership, document_type=document_type,
            period_start=period_start, supplier_code=supplier_code, project_id=project_id, query=query,
            page=page, page_size=page_size,
        )
        return JsonResponse({
            "ok": True,
            "sources": payload["results"],
            "supplierCode": supplier_code.upper(),
            "projectId": project_id,
            "period": period_start.strftime("%Y-%m"),
            "meta": _type_first_selector_meta(page=page, page_size=page_size, has_next=payload["hasNext"], query=query, document_type=document_type),
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_generator_review_api(request: HttpRequest) -> JsonResponse:
    """Review exactly one source after type -> supplier -> project/source selection."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        document_type = normalize_type_first_document_type(body.get("document_type"))
        period_start = _type_first_period(request, body)
        review = review_type_first_source(
            company=request.company, membership=request.company_membership, document_type=document_type,
            period_start=period_start, supplier_code=str(body.get("supplier_code") or ""),
            project_id=str(body.get("project_id") or ""), source_id=body.get("source_id"),
        )
        return JsonResponse({"ok": True, "review": review, "type": type_first_meta(document_type)})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_generator_create_api(request: HttpRequest) -> JsonResponse:
    """Finalize exactly one reviewed supplier-facing document from the type-first path."""
    stored_attachment = None
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        document_type = normalize_type_first_document_type(body.get("document_type"))
        period_start = _type_first_period(request, body)
        supplier_code = str(body.get("supplier_code") or "").strip().upper()
        project_id = str(body.get("project_id") or "").strip()
        source_id = body.get("source_id")
        # Re-resolve the exact source at commit time. This prevents a stale/tampered source id
        # from escaping the selected supplier, project, period or project-access scope.
        review = review_type_first_source(
            company=request.company, membership=request.company_membership, document_type=document_type,
            period_start=period_start, supplier_code=supplier_code, project_id=project_id, source_id=source_id,
        )

        invoice = None
        if document_type == DocumentType.SUPPLIER_INVOICE:
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
            document_type=document_type,
            source_id=source_id,
            invoice=invoice,
            supplier_code=supplier_code,
            request=request,
            allow_supplier_timesheet_pack=document_type == DocumentType.SUPPLIER_TIMESHEET_PACK,
        )
        if stored_attachment:
            actual_attachment = (((document.snapshot or {}).get("invoice") or {}).get("attachment") or {})
            if actual_attachment.get("storage_key") != stored_attachment.get("storage_key"):
                default_storage.delete(stored_attachment["storage_key"])
        return JsonResponse({
            "ok": True,
            "document": serialize_document(document, include_snapshot=True),
            "review": review,
        }, status=201)
    except Exception as exc:
        try:
            if stored_attachment and default_storage.exists(stored_attachment.get("storage_key", "")):
                default_storage.delete(stored_attachment["storage_key"])
        except Exception:
            pass
        return _errors(exc)


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


RENTAL_GENERATABLE_DOCUMENT_TYPES = {
    SUPPLIER_TIMESHEET_ALIAS,
    DocumentType.SUPPLIER_SETTLEMENT,
    DocumentType.RENTAL_TIMESHEET,
    DocumentType.SUPPLIER_PAYMENT_RECEIPT,
}


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    result: list[str] = []
    for item in items:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _rental_generation_filters(body: dict[str, object]) -> tuple[object, list[str], list[str], list[str]]:
    period_start = _period(str(body.get("period") or ""))
    if period_start is None:
        raise ValidationError({"period": "Period is required."})
    requested_types = _string_list(body.get("document_types"))
    if not requested_types:
        raise ValidationError({"document_types": "Select at least one document type."})
    unsupported = [item for item in requested_types if item not in RENTAL_GENERATABLE_DOCUMENT_TYPES]
    if unsupported:
        raise ValidationError({"document_types": f"Unsupported generated document type: {unsupported[0]}."})
    supplier_codes = [item.upper() for item in _string_list(body.get("supplier_codes"))]
    project_ids = _string_list(body.get("project_ids"))
    return period_start, requested_types, supplier_codes, project_ids


def _rental_generation_candidates(*, company, membership, period_start, requested_types, supplier_codes, project_ids):
    """Resolve exact eligible document units without hydrating high-cardinality masters.

    Each item is a single immutable output unit. Supplier-facing timesheets are supplier+project
    scoped; settlements are settlement scoped; project timesheets are project scoped; payment
    advice is payment scoped. Existing final documents stay visible in the plan and are skipped.
    """
    from apps.rental_manpower.models import (
        RentalTimesheetEntry, RentalTimesheetPeriod, RentalTimesheetStatus, RentalSettlementStatus,
        SupplierPayment, SupplierPaymentAllocation, SupplierPaymentStatus, SupplierSettlement,
    )

    allowed_projects = project_scope_ids(membership)
    requested_project_ids = set(project_ids)
    requested_suppliers = set(supplier_codes)
    items: list[dict[str, object]] = []

    def project_filter(qs, field: str):
        if allowed_projects is not None:
            qs = qs.filter(**{f"{field}__in": allowed_projects}) if allowed_projects else qs.none()
        if requested_project_ids:
            qs = qs.filter(**{f"{field}__in": requested_project_ids})
        return qs

    if SUPPLIER_TIMESHEET_ALIAS in requested_types:
        existing = BusinessDocument.objects.for_company(company).filter(
            document_type=DocumentType.RENTAL_TIMESHEET,
            source_id=OuterRef("period_id"),
            entity_reference=OuterRef("supplier_code"),
            snapshot__document_variant=SUPPLIER_TIMESHEET_VARIANT,
        )
        qs = RentalTimesheetEntry.objects.for_company(company).filter(
            period__period_start=period_start, period__status=RentalTimesheetStatus.LOCKED,
        )
        qs = project_filter(qs, "period__project_id")
        if requested_suppliers:
            qs = qs.filter(supplier_code__in=requested_suppliers)
        rows = (
            qs.values("period_id", "period__project_id", "project_code", "project_name", "supplier_code", "supplier_name")
            .distinct().annotate(_finalized=Exists(existing)).order_by("supplier_code", "project_code")[:501]
        )
        for row in rows:
            items.append({
                "key": f"supplier_timesheet:{row['period_id']}:{row['supplier_code']}",
                "type": SUPPLIER_TIMESHEET_ALIAS, "sourceId": str(row["period_id"]),
                "supplierCode": row["supplier_code"], "supplierName": row["supplier_name"],
                "projectId": str(row["period__project_id"]), "projectCode": row["project_code"], "projectName": row["project_name"],
                "label": f"{row['supplier_name']} · {row['project_name']}", "existing": bool(row["_finalized"]),
            })

    if DocumentType.SUPPLIER_SETTLEMENT in requested_types:
        final_statuses = [
            RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING,
            RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED,
        ]
        existing = BusinessDocument.objects.for_company(company).filter(
            document_type=DocumentType.SUPPLIER_SETTLEMENT, source_model="rental_manpower.suppliersettlement", source_id=OuterRef("pk"),
        )
        qs = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=final_statuses)
        qs = project_filter(qs, "project_id")
        if requested_suppliers:
            qs = qs.filter(supplier_code__in=requested_suppliers)
        for row in qs.annotate(_finalized=Exists(existing)).order_by("supplier_code", "project_code")[:501]:
            items.append({
                "key": f"supplier_settlement:{row.pk}", "type": DocumentType.SUPPLIER_SETTLEMENT, "sourceId": str(row.pk),
                "supplierCode": row.supplier_code, "supplierName": row.supplier_name, "projectId": str(row.project_id),
                "projectCode": row.project_code, "projectName": row.project_name,
                "label": f"{row.supplier_name} · {row.project_name}", "existing": bool(row._finalized),
            })

    if DocumentType.RENTAL_TIMESHEET in requested_types:
        existing = BusinessDocument.objects.for_company(company).filter(
            document_type=DocumentType.RENTAL_TIMESHEET, source_model="rental_manpower.rentaltimesheetperiod", source_id=OuterRef("pk"),
        )
        qs = RentalTimesheetPeriod.objects.for_company(company).filter(period_start=period_start, status=RentalTimesheetStatus.LOCKED)
        qs = project_filter(qs, "project_id")
        # Supplier filters do not change the internal all-supplier Project Timesheet.
        for row in qs.annotate(_finalized=Exists(existing)).select_related("project").order_by("project__code")[:501]:
            items.append({
                "key": f"rental_timesheet:{row.pk}", "type": DocumentType.RENTAL_TIMESHEET, "sourceId": str(row.pk),
                "supplierCode": "", "supplierName": "", "projectId": str(row.project_id),
                "projectCode": row.project.code, "projectName": row.project.name,
                "label": f"{row.project.code} · {row.project.name}", "existing": bool(row._finalized),
            })

    if DocumentType.SUPPLIER_PAYMENT_RECEIPT in requested_types:
        existing = BusinessDocument.objects.for_company(company).filter(
            document_type=DocumentType.SUPPLIER_PAYMENT_RECEIPT, source_model="rental_manpower.supplierpayment", source_id=OuterRef("pk"),
        )
        qs = SupplierPayment.objects.for_company(company).filter(
            allocations__settlement__period_start=period_start, status=SupplierPaymentStatus.PAID,
        ).distinct()
        if allowed_projects is not None:
            if not allowed_projects:
                qs = qs.none()
            else:
                outside = SupplierPaymentAllocation.objects.for_company(company).filter(payment_id=OuterRef("pk")).exclude(settlement__project_id__in=allowed_projects)
                qs = qs.annotate(_outside_scope=Exists(outside)).filter(_outside_scope=False)
        if requested_project_ids:
            qs = qs.filter(allocations__settlement__project_id__in=requested_project_ids)
        if requested_suppliers:
            qs = qs.filter(supplier_code__in=requested_suppliers)
        for row in qs.annotate(_finalized=Exists(existing)).distinct().order_by("supplier_code", "payment_number")[:501]:
            project_rows = list(row.allocations.filter(settlement__period_start=period_start).values_list("settlement__project_id", "settlement__project_code", "settlement__project_name").distinct()[:8])
            projects = ", ".join(code for _pid, code, _name in project_rows)
            items.append({
                "key": f"supplier_payment_receipt:{row.pk}", "type": DocumentType.SUPPLIER_PAYMENT_RECEIPT, "sourceId": str(row.pk),
                "supplierCode": row.supplier_code, "supplierName": row.supplier_name, "projectId": "",
                "projectCode": projects, "projectName": projects,
                "label": f"{row.supplier_name} · {row.payment_number}", "existing": bool(row._finalized),
            })

    if len(items) > 500:
        raise ValidationError("The generation plan exceeds 500 document units. Narrow the supplier or project scope.")
    return items


def _generation_request_fingerprint(*, period_start, requested_types, supplier_codes, project_ids, selected_keys, output_mode):
    payload = {
        "period": period_start.strftime("%Y-%m"),
        "document_types": sorted(requested_types),
        "supplier_codes": sorted(supplier_codes),
        "project_ids": sorted(str(value) for value in project_ids),
        "selected_keys": sorted(selected_keys),
        "output_mode": output_mode,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialize_generation_batch(event: AuditEvent) -> dict[str, object]:
    metadata = event.metadata or {}
    return {
        "id": str(event.id),
        "number": event.object_label,
        "period": metadata.get("period", ""),
        "documentTypes": metadata.get("document_types", []),
        "outputMode": metadata.get("output_mode", "separate_supplier_project"),
        "planned": int(metadata.get("planned_count", 0) or 0),
        "created": int(metadata.get("created_count", 0) or 0),
        "existing": int(metadata.get("skipped_existing_count", 0) or 0),
        "createdDocumentIds": metadata.get("created_document_ids", []),
        "createdDocumentNumbers": metadata.get("created_document_numbers", []),
        "createdAt": event.created_at.isoformat(),
        "initiatedBy": event.actor_display_name or event.actor_username or "System",
        "requestFingerprint": metadata.get("request_fingerprint", ""),
    }


def _generation_plan_payload(*, items, requested_types, period_start, supplier_codes, project_ids):
    counts: dict[str, dict[str, int]] = {}
    for document_type in requested_types:
        typed = [item for item in items if item["type"] == document_type]
        counts[document_type] = {
            "eligible": len(typed),
            "new": sum(1 for item in typed if not item["existing"]),
            "existing": sum(1 for item in typed if item["existing"]),
        }
    return {
        "period": period_start.strftime("%Y-%m"),
        "documentTypes": requested_types,
        "supplierCodes": supplier_codes,
        "projectIds": project_ids,
        "outputMode": "separate_supplier_project",
        "summary": {
            "eligible": len(items),
            "new": sum(1 for item in items if not item["existing"]),
            "existing": sum(1 for item in items if item["existing"]),
            "typeCounts": counts,
        },
        "items": items,
    }


@require_http_methods(["GET"])
@api_company_required
def document_generation_options_api(request: HttpRequest) -> JsonResponse:
    """Bounded supplier/project choices for the Rental document generator."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        supplier_q = request.GET.get("supplier_q", "").strip()
        project_q = request.GET.get("project_q", "").strip()
        from apps.rental_manpower.models import ManpowerSupplier, RentalTimesheetEntry, SupplierSettlement
        from apps.projects.models import Project

        # Final production closure: source options must never reveal supplier identities from
        # projects outside the membership's Rental project scope, and the selector must remain
        # server-searchable without hydrating every period source into Python.
        allowed_projects = project_scope_ids(request.company_membership)
        timesheet_sources = RentalTimesheetEntry.objects.for_company(request.company).filter(period__period_start=period_start)
        settlement_sources = SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start)
        if allowed_projects is not None:
            if allowed_projects:
                timesheet_sources = timesheet_sources.filter(period__project_id__in=allowed_projects)
                settlement_sources = settlement_sources.filter(project_id__in=allowed_projects)
            else:
                timesheet_sources = timesheet_sources.none()
                settlement_sources = settlement_sources.none()

        supplier_qs = (
            ManpowerSupplier.objects.for_company(request.company)
            .filter(deleted_at__isnull=True)
            .annotate(
                _has_timesheet_source=Exists(timesheet_sources.filter(supplier_code__iexact=OuterRef("code"))),
                _has_settlement_source=Exists(settlement_sources.filter(supplier_code__iexact=OuterRef("code"))),
            )
            .filter(Q(_has_timesheet_source=True) | Q(_has_settlement_source=True))
        )
        if supplier_q:
            supplier_qs = supplier_qs.filter(Q(code__icontains=supplier_q) | Q(name__icontains=supplier_q))

        project_qs = Project.objects.for_company(request.company).filter(deleted_at__isnull=True)
        if allowed_projects is not None:
            project_qs = project_qs.filter(pk__in=allowed_projects) if allowed_projects else project_qs.none()
        project_qs = (
            project_qs.annotate(
                _has_timesheet_source=Exists(timesheet_sources.filter(period__project_id=OuterRef("pk"))),
                _has_settlement_source=Exists(settlement_sources.filter(project_id=OuterRef("pk"))),
            )
            .filter(Q(_has_timesheet_source=True) | Q(_has_settlement_source=True))
        )
        if project_q:
            project_qs = project_qs.filter(Q(code__icontains=project_q) | Q(name__icontains=project_q))

        suppliers = [{"code": row.code, "name": row.name, "label": f"{row.code} · {row.name}"} for row in supplier_qs.order_by("code")[:100]]
        projects = [{"id": str(row.pk), "code": row.code, "name": row.name, "label": f"{row.code} · {row.name}"} for row in project_qs.order_by("code")[:100]]
        return JsonResponse({"ok": True, "suppliers": suppliers, "projects": projects, "period": period_start.strftime("%Y-%m")})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_generation_plan_api(request: HttpRequest) -> JsonResponse:
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        period_start, requested_types, supplier_codes, project_ids = _rental_generation_filters(body)
        items = _rental_generation_candidates(
            company=request.company, membership=request.company_membership, period_start=period_start,
            requested_types=requested_types, supplier_codes=supplier_codes, project_ids=project_ids,
        )
        return JsonResponse({"ok": True, "plan": _generation_plan_payload(
            items=items, requested_types=requested_types, period_start=period_start, supplier_codes=supplier_codes, project_ids=project_ids,
        )})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_generation_execute_api(request: HttpRequest) -> JsonResponse:
    """Create the reviewed Rental document plan atomically and append one immutable batch audit record."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot finalize Rental Manpower documents.")
        body = _body(request)
        period_start, requested_types, supplier_codes, project_ids = _rental_generation_filters(body)
        selected_keys = _string_list(body.get("selected_keys"))
        if not selected_keys:
            raise ValidationError({"selected_keys": "Select at least one reviewed document before creating the batch."})
        output_mode = str(body.get("output_mode") or "separate_supplier_project").strip()
        if output_mode != "separate_supplier_project":
            raise ValidationError({"output_mode": "Unsupported document output mode."})
        items = _rental_generation_candidates(
            company=request.company, membership=request.company_membership, period_start=period_start,
            requested_types=requested_types, supplier_codes=supplier_codes, project_ids=project_ids,
        )
        candidates_by_key = {str(item["key"]): item for item in items}
        missing_keys = [key for key in selected_keys if key not in candidates_by_key]
        if missing_keys:
            raise ValidationError({
                "selected_keys": "One or more reviewed documents are no longer eligible. Review the generation plan again."
            })
        selected = [candidates_by_key[key] for key in selected_keys]
        creatable = [item for item in selected if not item["existing"]]
        existing_count = sum(1 for item in selected if item["existing"])
        if len(creatable) > 200:
            raise ValidationError("Create at most 200 documents in one batch. Narrow the supplier or project scope.")
        fingerprint = _generation_request_fingerprint(
            period_start=period_start, requested_types=requested_types, supplier_codes=supplier_codes,
            project_ids=project_ids, selected_keys=[item["key"] for item in selected], output_mode=output_mode,
        )
        created = []
        batch_event = None
        with transaction.atomic():
            for item in creatable:
                kwargs = {
                    "actor_membership": request.company_membership, "document_type": item["type"],
                    "source_id": item["sourceId"], "request": request,
                }
                if item["type"] == SUPPLIER_TIMESHEET_ALIAS:
                    kwargs.update(document_variant=SUPPLIER_TIMESHEET_VARIANT, supplier_code=item["supplierCode"])
                document = finalize_business_document(**kwargs)
                created.append(serialize_document(document, include_snapshot=False))
            batch_number = allocate_number(
                company=request.company, key="document.generation_batch", prefix="DGB-", padding=7,
            )
            batch_event = record_audit_event(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.generation_batch_completed",
                object_type="documents.DocumentGenerationBatch", object_id=uuid.uuid4(), object_label=batch_number,
                actor_membership=request.company_membership, request=request,
                metadata={
                    "period": period_start.strftime("%Y-%m"),
                    "document_types": requested_types,
                    "supplier_codes": supplier_codes,
                    "project_ids": [str(value) for value in project_ids],
                    "selected_keys": [item["key"] for item in selected],
                    "output_mode": output_mode,
                    "planned_count": len(selected),
                    "created_count": len(created),
                    "skipped_existing_count": existing_count,
                    "created_document_ids": [item["id"] for item in created],
                    "created_document_numbers": [item["number"] for item in created],
                    "request_fingerprint": fingerprint,
                },
            )
        return JsonResponse({
            "ok": True, "created": len(created), "documents": created,
            "skippedExisting": existing_count, "batch": _serialize_generation_batch(batch_event),
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_generation_batches_api(request: HttpRequest) -> JsonResponse:
    """Return a bounded immutable history of completed Rental document-generation batches."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=False):
            raise PermissionDenied("Your access profile cannot view Rental Manpower documents.")
        period_start = _period(request.GET.get("period", ""))
        limit_raw = request.GET.get("limit", "5").strip()
        try:
            limit = max(1, min(20, int(limit_raw)))
        except ValueError as exc:
            raise ValidationError({"limit": "Limit must be a number between 1 and 20."}) from exc
        qs = AuditEvent.objects.filter(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.generation_batch_completed",
            object_type="documents.DocumentGenerationBatch",
        )
        if period_start is not None:
            qs = qs.filter(metadata__period=period_start.strftime("%Y-%m"))
        rows = list(qs.select_related("actor").order_by("-created_at")[:limit])
        return JsonResponse({"ok": True, "batches": [_serialize_generation_batch(row) for row in rows]})
    except Exception as exc:
        return _errors(exc)



DELIVERY_CHANNELS = {"email", "whatsapp", "hand", "portal", "other"}


def _delivery_pack_event(*, request: HttpRequest, pack_event_id) -> AuditEvent:
    pack_event = AuditEvent.objects.get(
        pk=pack_event_id, company=request.company, area=AuditArea.DOCUMENTS,
        action="documents.delivery_pack_issued", object_type="documents.DocumentDeliveryPack",
    )
    ids = []
    for value in (pack_event.metadata or {}).get("document_ids", []):
        try:
            ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("The document pack contains invalid document references.") from exc
    rows = list(
        documents_for_company(company=request.company, membership=request.company_membership, workspace="rental")
        .filter(pk__in=ids)
    )
    if len(rows) != len(ids):
        raise PermissionDenied("One or more pack documents are outside your current scope.")
    return pack_event


def _delivery_share_url(request: HttpRequest, pack_event: AuditEvent) -> str:
    token = make_delivery_share_token(pack_event)
    path = reverse("documents:delivery-pack-share", kwargs={"pack_event_id": pack_event.id, "token": token})
    return request.build_absolute_uri(path)


def _delivery_dispatched_event(pack_event: AuditEvent) -> AuditEvent | None:
    return AuditEvent.objects.filter(
        company=pack_event.company, area=AuditArea.DOCUMENTS,
        action="documents.delivery_pack_dispatched", object_type="documents.DocumentDeliveryPack",
        object_id=pack_event.object_id,
    ).order_by("-created_at", "-id").first()


def _delivery_opened_event(pack_event: AuditEvent) -> AuditEvent | None:
    return AuditEvent.objects.filter(
        company=pack_event.company, area=AuditArea.DOCUMENTS,
        action="documents.delivery_pack_opened", object_type="documents.DocumentDeliveryPack",
        object_id=pack_event.object_id,
    ).order_by("-created_at", "-id").first()


def _record_delivery_dispatched(*, request: HttpRequest, pack_event: AuditEvent, channel: str, transport: str, reference: str = "") -> AuditEvent:
    # Serialize the Sent transition on the immutable pack event so concurrent operator
    # confirmations cannot create duplicate dispatch evidence.
    with transaction.atomic():
        locked_pack = AuditEvent.objects.select_for_update().get(pk=pack_event.pk)
        existing = _delivery_dispatched_event(locked_pack)
        if existing:
            return existing
        metadata = locked_pack.metadata or {}
        ids = [uuid.UUID(str(value)) for value in metadata.get("document_ids", [])]
        rows = list(
            documents_for_company(company=request.company, membership=request.company_membership, workspace="rental")
            .filter(pk__in=ids)
        )
        if len(rows) != len(ids):
            raise PermissionDenied("One or more pack documents are outside your current scope.")
        if any(not verify_document_snapshot(row) for row in rows):
            raise PermissionDenied("One or more pack documents failed integrity verification.")
        sent_at = timezone.now().isoformat()
        dispatched = record_audit_event(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_dispatched",
            object_type="documents.DocumentDeliveryPack", object_id=locked_pack.object_id, object_label=locked_pack.object_label,
            actor_membership=request.company_membership, request=request,
            metadata={
                "issue_event_id": str(locked_pack.id), "channel": channel, "transport": transport,
                "reference": reference, "sent_at": sent_at,
                "recipient_name": metadata.get("recipient_name", ""),
                "recipient_email": metadata.get("recipient_email", ""),
                "recipient_phone": metadata.get("recipient_phone", ""),
            },
        )
        for row in rows:
            record_audit_event(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_sent",
                object_type="documents.BusinessDocument", object_id=row.id, object_label=row.document_number,
                actor_membership=request.company_membership, request=request,
                metadata={
                    "pack_event_id": str(locked_pack.id), "pack_number": locked_pack.object_label,
                    "supplier_code": metadata.get("supplier_code", ""),
                    "recipient_name": metadata.get("recipient_name", ""),
                    "recipient_email": metadata.get("recipient_email", ""),
                    "recipient_phone": metadata.get("recipient_phone", ""),
                    "channel": channel, "reference": reference or metadata.get("reference", ""),
                    "note": metadata.get("note", ""), "issued_at": metadata.get("issued_at", ""),
                    "sent_at": sent_at, "transport": transport,
                },
            )
        return dispatched


def _supplier_delivery_document(document: BusinessDocument) -> bool:
    return document.workspace == "rental" and bool(supplier_delivery_document_role(document))


def _supplier_delivery_document_payload(document: BusinessDocument, *, recommended: bool = False) -> dict[str, object]:
    payload = serialize_document(document)
    payload.update({
        "deliveryRole": supplier_delivery_document_role(document),
        "deliveryLabel": supplier_delivery_document_label(document),
        "deliveryFileName": supplier_delivery_filename(document),
        "isPrimaryDelivery": supplier_delivery_is_primary(document),
        "recommended": bool(recommended),
    })
    return payload


def _supplier_delivery_recommendations(rows: list[BusinessDocument]) -> set[str]:
    """Prefer one authoritative timesheet document per locked source for supplier issue.

    v3 Supplier Timesheet Packs are recommended. A legacy Supplier Timesheet Statement is
    recommended only where the source does not yet have a v3 pack. Settlement/payment documents
    remain opt-in because they belong to later commercial steps.
    """
    return {
        str(row.id)
        for row in prefer_v3_supplier_timesheets(rows)
        if supplier_delivery_document_role(row) in {"supplier_timesheet_pack", "legacy_supplier_timesheet"}
    }


def _document_supplier_code(document: BusinessDocument) -> str:
    snapshot = document.snapshot or {}
    supplier = snapshot.get("supplier") or {}
    return str(supplier.get("code") or document.entity_reference or "").strip().upper()


def _serialize_delivery_event(event: AuditEvent) -> dict[str, object]:
    metadata = event.metadata or {}
    action_label = {
        "documents.delivery_prepared": "Prepared",
        "documents.delivery_sent": "Sent",
        "documents.delivery_opened": "Opened",
        "documents.delivery_delivered": "Delivered",
    }.get(event.action, "Sent")
    return {
        "id": str(event.id),
        "action": action_label,
        "packNumber": metadata.get("pack_number", ""),
        "packEventId": metadata.get("pack_event_id", ""),
        "recipientName": metadata.get("recipient_name", ""),
        "recipientEmail": metadata.get("recipient_email", ""),
        "recipientPhone": metadata.get("recipient_phone", ""),
        "channel": metadata.get("channel", ""),
        "reference": metadata.get("reference", ""),
        "note": metadata.get("note", ""),
        "issuedAt": metadata.get("issued_at", ""),
        "createdAt": event.created_at.isoformat(),
        "actor": event.actor_display_name or event.actor_username or "System",
    }


def _delivery_history(*, company, document_id, limit: int = 20) -> list[dict[str, object]]:
    rows = AuditEvent.objects.filter(
        company=company, area=AuditArea.DOCUMENTS, object_type="documents.BusinessDocument",
        object_id=str(document_id), action__in=["documents.delivery_prepared", "documents.delivery_sent", "documents.delivery_opened", "documents.delivery_delivered"],
    ).order_by("-created_at", "-id")[:limit]
    return [_serialize_delivery_event(row) for row in rows]


def _serialize_delivery_pack(event: AuditEvent, *, request: HttpRequest | None = None) -> dict[str, object]:
    metadata = event.metadata or {}
    dispatched = _delivery_dispatched_event(event)
    opened = _delivery_opened_event(event)
    delivered = AuditEvent.objects.filter(
        company=event.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
        object_type="documents.DocumentDeliveryPack", object_id=event.object_id,
    ).order_by("-created_at").first()
    generation = delivery_share_generation(event)
    share_revoked = delivery_share_is_revoked(event, generation=generation)
    share_expires_at = delivery_share_expires_at(event, generation=generation)
    share_expired = delivery_share_is_expired(event, generation=generation)
    if delivered:
        status = "Delivered"
    elif opened:
        status = "Opened"
    elif dispatched:
        status = "Sent"
    else:
        status = "Prepared"
    payload = {
        "id": str(event.id),
        "number": event.object_label,
        "supplierCode": metadata.get("supplier_code", ""),
        "supplierName": metadata.get("supplier_name", ""),
        "recipientName": metadata.get("recipient_name", ""),
        "recipientEmail": metadata.get("recipient_email", ""),
        "recipientPhone": metadata.get("recipient_phone", ""),
        "channel": metadata.get("channel", ""),
        "reference": metadata.get("reference", ""),
        "note": metadata.get("note", ""),
        "documentIds": metadata.get("document_ids", []),
        "documentNumbers": metadata.get("document_numbers", []),
        "documents": metadata.get("document_manifest", []),
        "primaryDocumentIds": metadata.get("primary_document_ids", []),
        "primaryTimesheetNumbers": metadata.get("primary_timesheet_numbers", []),
        "deliveryContractVersion": metadata.get("delivery_contract_version", "1.0"),
        "acknowledgementScope": metadata.get("acknowledgement_scope", "receipt_only"),
        "issuedAt": metadata.get("issued_at", event.created_at.isoformat()),
        "issuedBy": event.actor_display_name or event.actor_username or "System",
        "status": status,
        "sentAt": dispatched.created_at.isoformat() if dispatched else "",
        "openedAt": opened.created_at.isoformat() if opened else "",
        "deliveredAt": delivered.created_at.isoformat() if delivered else "",
        "deliveredBy": (delivered.actor_display_name or delivered.actor_username or "System") if delivered else "",
        "printUrl": f"/documents/delivery-packs/{event.id}/print/",
        "shareTtlSeconds": delivery_share_ttl_seconds(),
        "shareGeneration": generation,
        "shareExpiresAt": share_expires_at.isoformat(),
        "shareExpired": share_expired,
        "shareStatus": "Revoked" if share_revoked else ("Expired" if share_expired else "Active"),
        "shareRevokedAt": (delivery_share_revoked_event(event, generation=generation).created_at.isoformat() if share_revoked else ""),
        "documentCount": len(metadata.get("document_ids", []) or []),
    }
    if request is not None:
        can_manage_delivery = _has_document_permission(request.company_membership, "rental", finalize=True)
        payload["shareUrl"] = "" if (share_revoked or share_expired or not can_manage_delivery) else _delivery_share_url(request, event)
    return payload


@require_http_methods(["GET"])
@api_company_required
def document_delivery_options_api(request: HttpRequest, document_id) -> JsonResponse:
    """Return one supplier-facing document's recipient defaults, compatible pack records and issue history."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=False):
            raise PermissionDenied("Your access profile cannot view Rental Manpower documents.")
        document = documents_for_company(company=request.company, membership=request.company_membership, workspace="rental").get(pk=document_id)
        if not _supplier_delivery_document(document):
            raise ValidationError("Only supplier-facing finalized documents can be issued to a supplier.")
        supplier_code = _document_supplier_code(document)
        from apps.rental_manpower.models import ManpowerSupplier
        supplier = ManpowerSupplier.objects.for_company(request.company).filter(code__iexact=supplier_code).first()
        recipient = {
            "name": (supplier.contact_person if supplier else "") or (supplier.name if supplier else document.entity_name),
            "email": supplier.email if supplier else "",
            "phone": supplier.phone if supplier else "",
        }
        compatible = documents_for_company(
            company=request.company, membership=request.company_membership, workspace="rental",
            period_start=document.period_start, entity_reference=supplier_code,
        ).order_by("document_type", "document_number")
        compatible_rows = prefer_v3_supplier_timesheets([row for row in compatible[:120] if _supplier_delivery_document(row)])
        recommended_ids = _supplier_delivery_recommendations(compatible_rows)
        default_channel = "email" if (supplier and supplier.email) else ("whatsapp" if (supplier and supplier.phone) else "portal")
        history = _delivery_history(company=request.company, document_id=document.id)
        pack_ids = []
        for item in history:
            value = str(item.get("packEventId") or "").strip()
            if value and value not in pack_ids:
                pack_ids.append(value)
        packs = list(
            AuditEvent.objects.filter(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
                object_type="documents.DocumentDeliveryPack", pk__in=pack_ids[:20],
            ).order_by("-created_at", "-id")
        )
        return JsonResponse({
            "ok": True,
            "supplier": {"code": supplier_code, "name": (supplier.name if supplier else document.entity_name)},
            "recipient": recipient,
            "recipientSource": "supplier_master" if supplier else "document_snapshot",
            "defaultChannel": default_channel,
            "deliveryContractVersion": SUPPLIER_DELIVERY_CONTRACT_VERSION,
            "documents": [
                _supplier_delivery_document_payload(row, recommended=str(row.id) in recommended_ids)
                for row in compatible_rows
            ],
            "recommendedDocumentIds": sorted(recommended_ids),
            "history": history,
            "packs": [_serialize_delivery_pack(row, request=request) for row in packs],
        })
    except Exception as exc:
        return _errors(exc)


def _issue_delivery_pack(*, request: HttpRequest, rows: list[BusinessDocument], recipient_name: str, recipient_email: str = "", recipient_phone: str = "", channel: str = "email", reference: str = "", note: str = "") -> AuditEvent:
    """Create one immutable supplier issue pack from already-scoped finalized documents."""
    if not rows:
        raise ValidationError({"document_ids": "Select one or more documents."})
    if len(rows) > 25:
        raise ValidationError({"document_ids": "A supplier issue pack is limited to 25 documents."})
    if any(not _supplier_delivery_document(row) for row in rows):
        raise ValidationError("Issue packs may contain only supplier-facing finalized documents.")
    if len(prefer_v3_supplier_timesheets(rows)) != len(rows):
        raise ValidationError("Do not issue a legacy Supplier Timesheet Statement together with its v3 Supplier Monthly Timesheet Pack.")
    if any(not verify_document_snapshot(row) for row in rows):
        raise ValidationError("One or more selected documents failed integrity verification.")
    supplier_codes = {_document_supplier_code(row) for row in rows}
    if len(supplier_codes) != 1 or not next(iter(supplier_codes), ""):
        raise ValidationError("All documents in an issue pack must belong to the same supplier.")
    supplier_code = next(iter(supplier_codes))
    from apps.rental_manpower.models import ManpowerSupplier
    supplier = ManpowerSupplier.objects.for_company(request.company).filter(code__iexact=supplier_code).first()
    supplier_name = supplier.name if supplier else rows[0].entity_name
    recipient_name = str(recipient_name or "").strip()
    recipient_email = str(recipient_email or "").strip().lower()
    recipient_phone = str(recipient_phone or "").strip()
    channel = str(channel or "email").strip().lower()
    reference = str(reference or "").strip()[:120]
    note = str(note or "").strip()[:500]
    if not recipient_name:
        raise ValidationError({"recipient_name": f"Recipient name is required for {supplier_name or supplier_code}."})
    if channel not in DELIVERY_CHANNELS:
        raise ValidationError({"channel": "Select a valid delivery channel."})
    if channel == "email":
        if not recipient_email:
            raise ValidationError({"recipient_email": f"Recipient email is required for {supplier_name or supplier_code}."})
        validate_email(recipient_email)
    if channel == "whatsapp" and not recipient_phone:
        raise ValidationError({"recipient_phone": f"Recipient phone is required for {supplier_name or supplier_code}."})
    issued_at = timezone.now().isoformat()
    document_manifest = [supplier_delivery_manifest_entry(row) for row in rows]
    primary_document_ids = [row["id"] for row in document_manifest if row.get("primary")]
    primary_timesheet_numbers = [row["number"] for row in document_manifest if row.get("primary")]
    pack_number = allocate_number(company=request.company, key="document.delivery_pack", prefix="DIP-", padding=7)
    pack_event = record_audit_event(
        company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
        object_type="documents.DocumentDeliveryPack", object_id=uuid.uuid4(), object_label=pack_number,
        actor_membership=request.company_membership, request=request,
        metadata={
            "supplier_code": supplier_code, "supplier_name": supplier_name,
            "recipient_name": recipient_name, "recipient_email": recipient_email, "recipient_phone": recipient_phone,
            "channel": channel, "reference": reference, "note": note, "issued_at": issued_at,
            "delivery_contract_version": SUPPLIER_DELIVERY_CONTRACT_VERSION,
            "acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
            "document_ids": [str(row.id) for row in rows], "document_numbers": [row.document_number for row in rows],
            "document_manifest": document_manifest,
            "primary_document_ids": primary_document_ids, "primary_timesheet_numbers": primary_timesheet_numbers,
            "periods": sorted({row.period_start.strftime("%Y-%m") for row in rows if row.period_start}),
        },
    )
    for row in rows:
        record_audit_event(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_prepared",
            object_type="documents.BusinessDocument", object_id=row.id, object_label=row.document_number,
            actor_membership=request.company_membership, request=request,
            metadata={
                "pack_event_id": str(pack_event.id), "pack_number": pack_number,
                "supplier_code": supplier_code, "recipient_name": recipient_name,
                "recipient_email": recipient_email, "recipient_phone": recipient_phone,
                "channel": channel, "reference": reference, "note": note, "issued_at": issued_at,
                "delivery_contract_version": SUPPLIER_DELIVERY_CONTRACT_VERSION,
                "acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
                "delivery_role": supplier_delivery_document_role(row),
                "delivery_file_name": supplier_delivery_filename(row),
            },
        )
    return pack_event


def _delivery_center_document_queryset(*, request: HttpRequest, period_start, query: str = ""):
    qs = documents_for_company(
        company=request.company, membership=request.company_membership, workspace="rental", period_start=period_start,
    ).filter(
        Q(document_type__in=[DocumentType.SUPPLIER_TIMESHEET_PACK, DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_PAYMENT_RECEIPT])
        | Q(document_type=DocumentType.RENTAL_TIMESHEET, snapshot__document_variant=SUPPLIER_TIMESHEET_VARIANT)
    )
    q = str(query or "").strip()[:120]
    if q:
        qs = qs.filter(
            Q(document_number__icontains=q) | Q(title__icontains=q) | Q(entity_reference__icontains=q)
            | Q(entity_name__icontains=q) | Q(source_reference__icontains=q)
        )
    return qs.order_by("entity_reference", "document_type", "document_number")


@require_http_methods(["GET"])
@api_company_required
def document_delivery_center_api(request: HttpRequest) -> JsonResponse:
    """Return a bounded supplier-oriented issue workspace for one payroll period."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=False):
            raise PermissionDenied("Your access profile cannot view Rental Manpower documents.")
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        rows = list(_delivery_center_document_queryset(
            request=request, period_start=period_start, query=request.GET.get("q", ""),
        )[:501])
        truncated = len(rows) > 500
        rows = prefer_v3_supplier_timesheets(rows[:500])
        recommended_ids = _supplier_delivery_recommendations(rows)
        supplier_codes = sorted({_document_supplier_code(row) for row in rows if _document_supplier_code(row)})
        from apps.rental_manpower.models import ManpowerSupplier
        suppliers = {
            str(item.code).strip().upper(): item
            for item in ManpowerSupplier.objects.for_company(request.company).filter(code__in=supplier_codes)
        }
        page_ids = [str(row.id) for row in rows]
        latest_delivery: dict[str, dict[str, object]] = {}
        if page_ids:
            events = AuditEvent.objects.filter(
                company=request.company, area=AuditArea.DOCUMENTS, object_type="documents.BusinessDocument",
                object_id__in=page_ids,
                action__in=["documents.delivery_prepared", "documents.delivery_sent", "documents.delivery_opened", "documents.delivery_delivered"],
            ).order_by("-created_at", "-id")
            for event in events:
                if event.object_id in latest_delivery:
                    continue
                latest_delivery[event.object_id] = _serialize_delivery_event(event)
        groups: dict[str, dict[str, object]] = {}
        for row in rows:
            code = _document_supplier_code(row)
            if not code:
                continue
            supplier = suppliers.get(code)
            group = groups.setdefault(code, {
                "supplierCode": code,
                "supplierName": (supplier.name if supplier else row.entity_name) or code,
                "recipient": {
                    "name": ((supplier.contact_person if supplier else "") or (supplier.name if supplier else row.entity_name) or code),
                    "email": supplier.email if supplier else "",
                    "phone": supplier.phone if supplier else "",
                },
                "documents": [],
            })
            delivery = latest_delivery.get(str(row.id))
            item = _supplier_delivery_document_payload(row, recommended=str(row.id) in recommended_ids)
            item["delivery"] = {
                "status": (delivery or {}).get("action", "Not issued"),
                "packNumber": (delivery or {}).get("packNumber", ""),
                "packEventId": (delivery or {}).get("packEventId", ""),
            }
            group["documents"].append(item)
        period_key = period_start.strftime("%Y-%m")
        recent = list(AuditEvent.objects.filter(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack", metadata__periods__contains=[period_key],
        ).order_by("-created_at", "-id")[:10])
        return JsonResponse({
            "ok": True,
            "period": period_key,
            "groups": list(groups.values()),
            "recentPacks": [_serialize_delivery_pack(event, request=request) for event in recent],
            "deliveryContractVersion": SUPPLIER_DELIVERY_CONTRACT_VERSION,
            "meta": {
                "documents": len(rows), "suppliers": len(groups), "recommended": len(recommended_ids),
                "truncated": truncated, "limit": 500,
            },
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_delivery_operations_api(request: HttpRequest) -> JsonResponse:
    """Return bounded supplier issue-pack lifecycle data for operational follow-up."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=False):
            raise PermissionDenied("Your access profile cannot view Rental Manpower documents.")
        period_start = _period(request.GET.get("period", ""))
        if period_start is None:
            raise ValidationError({"period": "Period is required."})
        period_key = period_start.strftime("%Y-%m")
        query = str(request.GET.get("q") or "").strip().lower()[:120]
        status_filter = str(request.GET.get("status") or "all").strip().lower()[:30]
        candidates = list(AuditEvent.objects.filter(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack", metadata__periods__contains=[period_key],
        ).order_by("-created_at", "-id")[:501])
        truncated = len(candidates) > 500
        candidates = candidates[:500]
        matched = []
        for event in candidates:
            pack = _serialize_delivery_pack(event, request=request)
            haystack = " ".join([
                str(pack.get("number") or ""), str(pack.get("supplierCode") or ""),
                str(pack.get("supplierName") or ""), str(pack.get("recipientName") or ""),
                str(pack.get("recipientEmail") or ""), str(pack.get("reference") or ""),
                " ".join(str(value) for value in (pack.get("documentNumbers") or [])),
            ]).lower()
            if query and query not in haystack:
                continue
            matched.append(pack)
        summary = {"total": len(matched), "prepared": 0, "sent": 0, "opened": 0, "delivered": 0, "attention": 0}
        for pack in matched:
            lifecycle = str(pack.get("status") or "Prepared").lower()
            if lifecycle in summary:
                summary[lifecycle] += 1
            if lifecycle != "delivered" and str(pack.get("shareStatus") or "Active") in {"Revoked", "Expired"}:
                summary["attention"] += 1
        rows = []
        for pack in matched:
            lifecycle = str(pack.get("status") or "Prepared").lower()
            share_state = str(pack.get("shareStatus") or "Active").lower()
            if status_filter not in {"", "all"}:
                if status_filter == "attention":
                    if lifecycle == "delivered" or share_state == "active":
                        continue
                elif status_filter not in {lifecycle, share_state}:
                    continue
            rows.append(pack)
        return JsonResponse({
            "ok": True, "period": period_key, "packs": rows[:100], "summary": summary,
            "meta": {"count": len(rows), "returned": min(len(rows), 100), "truncated": truncated or len(rows) > 100, "limit": 100},
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_batch_prepare_api(request: HttpRequest) -> JsonResponse:
    """Prepare separate immutable issue packs for multiple suppliers in one reviewed action."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot issue Rental Manpower documents.")
        body = _body(request)
        raw_ids = body.get("document_ids") or []
        if not isinstance(raw_ids, list):
            raise ValidationError({"document_ids": "Select one or more documents."})
        document_ids = []
        for value in raw_ids:
            try:
                parsed = uuid.UUID(str(value))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError({"document_ids": "One or more document IDs are invalid."}) from exc
            if parsed not in document_ids:
                document_ids.append(parsed)
        if not document_ids or len(document_ids) > 200:
            raise ValidationError({"document_ids": "Select between 1 and 200 supplier documents."})
        rows = list(documents_for_company(
            company=request.company, membership=request.company_membership, workspace="rental",
        ).filter(pk__in=document_ids).order_by("entity_reference", "document_number"))
        if len(rows) != len(document_ids):
            raise PermissionDenied("One or more selected documents are outside your document scope.")
        if any(not _supplier_delivery_document(row) for row in rows):
            raise ValidationError("Bulk issue may contain only supplier-facing finalized documents.")
        grouped: dict[str, list[BusinessDocument]] = {}
        for row in rows:
            code = _document_supplier_code(row)
            if not code:
                raise ValidationError("One or more selected documents do not have a supplier identity.")
            grouped.setdefault(code, []).append(row)
        if len(grouped) > 25:
            raise ValidationError("Bulk issue is limited to 25 suppliers at a time.")
        if any(len(items) > 25 for items in grouped.values()):
            raise ValidationError("A supplier issue pack is limited to 25 documents. Narrow the selection for that supplier.")
        channel = str(body.get("channel") or "email").strip().lower()
        if channel not in DELIVERY_CHANNELS:
            raise ValidationError({"channel": "Select a valid delivery channel."})
        reference = str(body.get("reference") or "").strip()[:120]
        note = str(body.get("note") or "").strip()[:500]
        from apps.rental_manpower.models import ManpowerSupplier
        suppliers = {
            str(item.code).strip().upper(): item
            for item in ManpowerSupplier.objects.for_company(request.company).filter(code__in=list(grouped))
        }
        recipient_by_supplier: dict[str, dict[str, str]] = {}
        errors = []
        for code, items in grouped.items():
            supplier = suppliers.get(code)
            supplier_name = (supplier.name if supplier else items[0].entity_name) or code
            recipient = {
                "name": ((supplier.contact_person if supplier else "") or supplier_name),
                "email": str(supplier.email if supplier else "").strip().lower(),
                "phone": str(supplier.phone if supplier else "").strip(),
            }
            if channel == "email" and not recipient["email"]:
                errors.append(f"{supplier_name}: email is missing")
            if channel == "whatsapp" and not recipient["phone"]:
                errors.append(f"{supplier_name}: phone is missing")
            recipient_by_supplier[code] = recipient
        if errors:
            raise ValidationError({"recipients": errors[:25]})
        with transaction.atomic():
            pack_events = []
            for code in sorted(grouped):
                recipient = recipient_by_supplier[code]
                pack_events.append(_issue_delivery_pack(
                    request=request, rows=grouped[code], recipient_name=recipient["name"],
                    recipient_email=recipient["email"], recipient_phone=recipient["phone"],
                    channel=channel, reference=reference, note=note,
                ))
            batch_number = allocate_number(company=request.company, key="document.delivery_batch", prefix="DIB-", padding=7)
            batch_event = record_audit_event(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_batch_prepared",
                object_type="documents.DocumentDeliveryBatch", object_id=uuid.uuid4(), object_label=batch_number,
                actor_membership=request.company_membership, request=request,
                metadata={
                    "channel": channel, "reference": reference, "note": note,
                    "supplier_codes": sorted(grouped), "document_count": len(rows), "pack_count": len(pack_events),
                    "pack_event_ids": [str(event.id) for event in pack_events],
                    "pack_numbers": [event.object_label for event in pack_events],
                },
            )
        return JsonResponse({
            "ok": True,
            "batch": {"id": str(batch_event.id), "number": batch_event.object_label, "packCount": len(pack_events), "documentCount": len(rows)},
            "packs": [_serialize_delivery_pack(event, request=request) for event in pack_events],
        }, status=201)
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_pack_api(request: HttpRequest) -> JsonResponse:
    """Issue one immutable supplier delivery pack without changing finalized document records."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot issue Rental Manpower documents.")
        body = _body(request)
        raw_ids = body.get("document_ids") or []
        if not isinstance(raw_ids, list):
            raise ValidationError({"document_ids": "Select one or more documents."})
        document_ids = []
        for value in raw_ids:
            try:
                parsed = uuid.UUID(str(value))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError({"document_ids": "One or more document IDs are invalid."}) from exc
            if parsed not in document_ids:
                document_ids.append(parsed)
        if not document_ids or len(document_ids) > 25:
            raise ValidationError({"document_ids": "Select between 1 and 25 documents for one supplier issue pack."})
        rows = list(documents_for_company(
            company=request.company, membership=request.company_membership, workspace="rental",
        ).filter(pk__in=document_ids).order_by("document_number"))
        if len(rows) != len(document_ids):
            raise PermissionDenied("One or more selected documents are outside your document scope.")
        if any(not _supplier_delivery_document(row) for row in rows):
            raise ValidationError("Issue packs may contain only supplier-facing finalized documents.")
        supplier_codes = {_document_supplier_code(row) for row in rows}
        if len(supplier_codes) != 1 or not next(iter(supplier_codes), ""):
            raise ValidationError("All documents in an issue pack must belong to the same supplier.")
        pack_event = _issue_delivery_pack(
            request=request, rows=rows,
            recipient_name=str(body.get("recipient_name") or ""),
            recipient_email=str(body.get("recipient_email") or ""),
            recipient_phone=str(body.get("recipient_phone") or ""),
            channel=str(body.get("channel") or "email"),
            reference=str(body.get("reference") or ""), note=str(body.get("note") or ""),
        )
        return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request)}, status=201)
    except Exception as exc:
        return _errors(exc)


def _dispatch_delivery_pack_email(*, request: HttpRequest, pack_event: AuditEvent) -> tuple[str, str]:
    """Send one prepared email pack and return (result, share_url). Existing sends are never duplicated."""
    # Hold a row lock across the external send so two concurrent requests for the same pack
    # cannot both pass the retry-safe check and emit duplicate supplier emails.
    with transaction.atomic():
        pack_event = AuditEvent.objects.select_for_update().get(pk=pack_event.pk)
        metadata = pack_event.metadata or {}
        if delivery_share_is_revoked(pack_event):
            raise ValidationError("Supplier link is revoked. Reissue the link before sending this pack.")
        if delivery_share_is_expired(pack_event):
            raise ValidationError("Supplier link has expired. Reissue the link before sending this pack.")
        share_url = _delivery_share_url(request, pack_event)
        if _delivery_dispatched_event(pack_event):
            return "already_sent", share_url
        recipient_email = str(metadata.get("recipient_email") or "").strip().lower()
        if not recipient_email:
            raise ValidationError({"recipient_email": "Recipient email is required."})
        validate_email(recipient_email)
        if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and not settings.EMAIL_HOST:
            raise ValidationError("Outbound email is not configured on this server.")
        supplier_name = str(metadata.get("supplier_name") or "Supplier")
        pack_number = pack_event.object_label
        reference = str(metadata.get("reference") or "").strip()
        document_numbers = [str(value) for value in metadata.get("document_numbers", [])]
        manifest = metadata.get("document_manifest") or []
        primary_numbers = [str(value) for value in metadata.get("primary_timesheet_numbers", [])]
        periods = [str(value) for value in metadata.get("periods", []) if value]
        period_label = ", ".join(periods)
        if len(manifest) == 1 and primary_numbers:
            subject = f"SESCCO Supplier Timesheet · {period_label or pack_number} · {supplier_name}"
        else:
            subject = f"SESCCO supplier documents · {period_label or pack_number} · {supplier_name}"
        document_lines = [
            f"- {row.get('label') or row.get('number')}: {row.get('file_name') or row.get('number')}"
            for row in manifest if isinstance(row, dict)
        ]
        if not document_lines and document_numbers:
            document_lines = [f"- {value}" for value in document_numbers]
        lines = [
            supplier_name,
            f"Issue pack: {pack_number}",
            f"Service period: {period_label}" if period_label else "",
            f"Reference: {reference}" if reference else "",
            "",
            "Documents:",
            *document_lines,
            "",
            f"Open secure documents: {share_url}",
            "Acknowledgement confirms receipt only; it does not change timesheet or settlement approval authority.",
        ]
        body = "\n".join(line for line in lines if line is not None)
        html_docs = "".join(
            f"<li>{escape(str(row.get('label') or row.get('number') or 'Document'))}<br><small>{escape(str(row.get('file_name') or row.get('number') or ''))}</small></li>"
            for row in manifest if isinstance(row, dict)
        )
        html = (
            f"<p><strong>{escape(supplier_name)}</strong></p>"
            f"<p>{escape(pack_number)}{(' · ' + escape(period_label)) if period_label else ''}</p>"
            f"<ul>{html_docs}</ul>"
            f"<p><a href=\"{escape(share_url)}\">Open secure documents</a></p>"
            f"<p><small>Acknowledgement confirms receipt only; it does not change timesheet or settlement approval authority.</small></p>"
        )
        message = EmailMultiAlternatives(subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient_email])
        message.attach_alternative(html, "text/html")
        sent_count = message.send(fail_silently=False)
        if sent_count != 1:
            raise ValidationError("Email delivery was not accepted by the configured mail server.")
        _record_delivery_dispatched(request=request, pack_event=pack_event, channel="email", transport="smtp", reference=reference)
        return "sent", share_url


@require_http_methods(["POST"])
@api_company_required
def document_delivery_dispatch_api(request: HttpRequest, pack_event_id) -> JsonResponse:
    """Dispatch a prepared issue pack through the selected outbound channel."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot send Rental Manpower documents.")
        pack_event = _delivery_pack_event(request=request, pack_event_id=pack_event_id)
        metadata = pack_event.metadata or {}
        channel = str(metadata.get("channel") or "").strip().lower()
        if delivery_share_is_revoked(pack_event):
            raise ValidationError("Supplier link is revoked. Reissue the link before sending this pack.")
        if delivery_share_is_expired(pack_event):
            raise ValidationError("Supplier link has expired. Reissue the link before sending this pack.")
        share_url = _delivery_share_url(request, pack_event)
        existing = _delivery_dispatched_event(pack_event)
        if existing:
            return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request), "shareUrl": share_url})
        if channel == "email":
            _dispatch_delivery_pack_email(request=request, pack_event=pack_event)
            return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request), "shareUrl": share_url})
        if channel == "whatsapp":
            phone = "".join(ch for ch in str(metadata.get("recipient_phone") or "") if ch.isdigit())
            if not phone:
                raise ValidationError({"recipient_phone": "Recipient phone is required."})
            message = f"SESCCO documents {pack_event.object_label}: {share_url}"
            return JsonResponse({
                "ok": True, "pack": _serialize_delivery_pack(pack_event, request=request), "shareUrl": share_url,
                "handoffUrl": f"https://wa.me/{phone}?text={quote(message)}", "requiresConfirmation": True,
            })
        return JsonResponse({
            "ok": True, "pack": _serialize_delivery_pack(pack_event, request=request), "shareUrl": share_url,
            "requiresConfirmation": True,
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_batch_dispatch_api(request: HttpRequest, batch_event_id) -> JsonResponse:
    """Dispatch or confirm every prepared pack in one delivery batch without duplicating successful sends."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot send Rental Manpower documents.")
        batch_event = AuditEvent.objects.get(
            pk=batch_event_id, company=request.company, area=AuditArea.DOCUMENTS,
            action="documents.delivery_batch_prepared", object_type="documents.DocumentDeliveryBatch",
        )
        batch_meta = batch_event.metadata or {}
        raw_pack_ids = batch_meta.get("pack_event_ids") or []
        if not isinstance(raw_pack_ids, list) or not raw_pack_ids or len(raw_pack_ids) > 25:
            raise ValidationError("This delivery batch does not contain a valid bounded supplier pack set.")
        pack_events = []
        for value in raw_pack_ids:
            try:
                pack_id = uuid.UUID(str(value))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError("This delivery batch contains an invalid supplier pack reference.") from exc
            pack_events.append(_delivery_pack_event(request=request, pack_event_id=pack_id))
        channel = str(batch_meta.get("channel") or "").strip().lower()
        if channel not in DELIVERY_CHANNELS:
            raise ValidationError("This delivery batch has an invalid channel.")
        for pack_event in pack_events:
            if str((pack_event.metadata or {}).get("channel") or "").strip().lower() != channel:
                raise ValidationError("This delivery batch contains packs with mismatched channels.")
        body = _body(request)
        confirm = bool(body.get("confirm"))
        if channel == "whatsapp":
            raise ValidationError("WhatsApp packs require individual handoff confirmation for each supplier.")
        if channel != "email" and not confirm:
            raise ValidationError("Confirm the completed handoff before marking all supplier packs sent.")

        results = []
        sent_ids = []
        already_ids = []
        failed = []
        for pack_event in pack_events:
            try:
                if _delivery_dispatched_event(pack_event):
                    already_ids.append(str(pack_event.id))
                    result = "already_sent"
                    share_url = "" if delivery_share_is_revoked(pack_event) else _delivery_share_url(request, pack_event)
                elif channel == "email":
                    result, share_url = _dispatch_delivery_pack_email(request=request, pack_event=pack_event)
                    sent_ids.append(str(pack_event.id))
                else:
                    if delivery_share_is_revoked(pack_event):
                        raise ValidationError("Supplier link is revoked. Reissue the link before confirming this pack.")
                    if delivery_share_is_expired(pack_event):
                        raise ValidationError("Supplier link has expired. Reissue the link before confirming this pack.")
                    share_url = _delivery_share_url(request, pack_event)
                    transport = "portal" if channel == "portal" else "operator_confirmed"
                    reference = str((pack_event.metadata or {}).get("reference") or "").strip()[:120]
                    _record_delivery_dispatched(
                        request=request, pack_event=pack_event, channel=channel,
                        transport=transport, reference=reference,
                    )
                    sent_ids.append(str(pack_event.id))
                    result = "sent"
                results.append({
                    "id": str(pack_event.id), "number": pack_event.object_label, "result": result,
                    "pack": _serialize_delivery_pack(pack_event, request=request), "shareUrl": share_url,
                })
            except Exception as exc:
                if isinstance(exc, ValidationError):
                    if hasattr(exc, "message_dict"):
                        messages = [str(item) for values in exc.message_dict.values() for item in values]
                    else:
                        messages = [str(item) for item in exc.messages]
                    message = "; ".join(messages) or "Delivery failed."
                else:
                    message = str(exc) or "Delivery failed."
                failed.append({"id": str(pack_event.id), "number": pack_event.object_label, "error": message[:500]})
                results.append({"id": str(pack_event.id), "number": pack_event.object_label, "result": "failed", "error": message[:500]})

        attempt_event = record_audit_event(
            company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_batch_dispatched",
            object_type="documents.DocumentDeliveryBatch", object_id=batch_event.object_id, object_label=batch_event.object_label,
            actor_membership=request.company_membership, request=request,
            metadata={
                "prepared_event_id": str(batch_event.id), "channel": channel,
                "pack_count": len(pack_events), "sent_count": len(sent_ids), "already_sent_count": len(already_ids),
                "failed_count": len(failed), "sent_pack_event_ids": sent_ids,
                "already_sent_pack_event_ids": already_ids, "failed": failed,
            },
        )
        return JsonResponse({
            "ok": True,
            "batch": {
                "id": str(batch_event.id), "number": batch_event.object_label, "dispatchEventId": str(attempt_event.id),
                "channel": channel, "total": len(pack_events), "sent": len(sent_ids),
                "alreadySent": len(already_ids), "failed": len(failed),
            },
            "results": results,
        })
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_confirm_sent_api(request: HttpRequest, pack_event_id) -> JsonResponse:
    """Record operator-confirmed send/handoff for non-SMTP channels."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot confirm supplier document sending.")
        pack_event = _delivery_pack_event(request=request, pack_event_id=pack_event_id)
        metadata = pack_event.metadata or {}
        channel = str(metadata.get("channel") or "other").strip().lower()
        if channel == "email" and not _delivery_dispatched_event(pack_event):
            raise ValidationError("Email issue packs must be sent through the configured mail server.")
        body = _body(request)
        reference = str(body.get("reference") or metadata.get("reference") or "").strip()[:120]
        transport = "operator_confirmed" if channel != "portal" else "portal"
        _record_delivery_dispatched(request=request, pack_event=pack_event, channel=channel, transport=transport, reference=reference)
        return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request)})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_share_revoke_api(request: HttpRequest, pack_event_id) -> JsonResponse:
    """Revoke the current supplier share generation without mutating the issued document pack."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot revoke supplier document links.")
        pack_event = _delivery_pack_event(request=request, pack_event_id=pack_event_id)
        body = _body(request)
        note = str(body.get("note") or "").strip()[:500]
        with transaction.atomic():
            pack_event = AuditEvent.objects.select_for_update().get(pk=pack_event.pk)
            generation = delivery_share_generation(pack_event)
            if not delivery_share_is_revoked(pack_event, generation=generation):
                record_audit_event(
                    company=request.company, area=AuditArea.DOCUMENTS, action=DELIVERY_SHARE_REVOKED_ACTION,
                    object_type="documents.DocumentDeliveryPack", object_id=pack_event.object_id, object_label=pack_event.object_label,
                    actor_membership=request.company_membership, request=request,
                    metadata={"issue_event_id": str(pack_event.id), "generation": generation, "note": note},
                )
        return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request)})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_share_reissue_api(request: HttpRequest, pack_event_id) -> JsonResponse:
    """Rotate a supplier share link so every older token becomes unusable immediately."""
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot reissue supplier document links.")
        pack_event = _delivery_pack_event(request=request, pack_event_id=pack_event_id)
        body = _body(request)
        note = str(body.get("note") or "").strip()[:500]
        with transaction.atomic():
            pack_event = AuditEvent.objects.select_for_update().get(pk=pack_event.pk)
            generation = delivery_share_generation(pack_event) + 1
            record_audit_event(
                company=request.company, area=AuditArea.DOCUMENTS, action=DELIVERY_SHARE_REISSUED_ACTION,
                object_type="documents.DocumentDeliveryPack", object_id=pack_event.object_id, object_label=pack_event.object_label,
                actor_membership=request.company_membership, request=request,
                metadata={"issue_event_id": str(pack_event.id), "generation": generation, "note": note},
            )
        payload = _serialize_delivery_pack(pack_event, request=request)
        return JsonResponse({"ok": True, "pack": payload, "shareUrl": payload.get("shareUrl", "")})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["POST"])
@api_company_required
def document_delivery_mark_delivered_api(request: HttpRequest, pack_event_id) -> JsonResponse:
    try:
        if not _has_document_permission(request.company_membership, "rental", finalize=True):
            raise PermissionDenied("Your access profile cannot confirm supplier document delivery.")
        scoped_pack = _delivery_pack_event(request=request, pack_event_id=pack_event_id)
        body = _body(request)
        reference = str(body.get("reference") or "").strip()[:120]
        note = str(body.get("note") or "").strip()[:500]
        with transaction.atomic():
            pack_event = AuditEvent.objects.select_for_update().get(pk=scoped_pack.pk)
            metadata = pack_event.metadata or {}
            ids = [uuid.UUID(str(value)) for value in metadata.get("document_ids", [])]
            rows = list(documents_for_company(company=request.company, membership=request.company_membership, workspace="rental").filter(pk__in=ids))
            if len(rows) != len(ids):
                raise PermissionDenied("One or more pack documents are outside your current scope.")
            if any(not verify_document_snapshot(row) for row in rows):
                raise PermissionDenied("One or more pack documents failed integrity verification.")
            existing = AuditEvent.objects.filter(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
                object_type="documents.DocumentDeliveryPack", object_id=pack_event.object_id,
            ).order_by("-created_at").first()
            if existing:
                return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request)})
            if _delivery_dispatched_event(pack_event) is None and _delivery_opened_event(pack_event) is None:
                raise ValidationError("Mark the supplier pack Sent before confirming delivery.")
            delivered_event = record_audit_event(
                company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
                object_type="documents.DocumentDeliveryPack", object_id=pack_event.object_id, object_label=pack_event.object_label,
                actor_membership=request.company_membership, request=request,
                metadata={"issue_event_id": str(pack_event.id), "reference": reference, "note": note},
            )
            for row in rows:
                record_audit_event(
                    company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_delivered",
                    object_type="documents.BusinessDocument", object_id=row.id, object_label=row.document_number,
                    actor_membership=request.company_membership, request=request,
                    metadata={
                        "pack_event_id": str(pack_event.id), "pack_number": pack_event.object_label,
                        "supplier_code": metadata.get("supplier_code", ""), "recipient_name": metadata.get("recipient_name", ""),
                        "recipient_email": metadata.get("recipient_email", ""), "recipient_phone": metadata.get("recipient_phone", ""),
                        "channel": metadata.get("channel", ""), "reference": reference or metadata.get("reference", ""),
                        "note": note, "issued_at": metadata.get("issued_at", ""), "delivered_event_id": str(delivered_event.id),
                    },
                )
        return JsonResponse({"ok": True, "pack": _serialize_delivery_pack(pack_event, request=request)})
    except Exception as exc:
        return _errors(exc)


@require_http_methods(["GET"])
@api_company_required
def document_detail_api(request: HttpRequest, document_id) -> JsonResponse:
    try:
        summary_only = request.GET.get("view", "").strip().lower() == "summary"
        row_qs = documents_for_company(company=request.company, membership=request.company_membership)
        # Summary previews deliberately defer the immutable snapshot. Full detail remains
        # available for existing API consumers, while print/share routes independently verify
        # the snapshot before rendering authoritative output.
        row = (row_qs.defer("snapshot") if summary_only else row_qs).get(pk=document_id)
        history = _delivery_history(company=request.company, document_id=row.id) if row.workspace == "rental" else []
        delivery = history[0] if history else None
        if delivery:
            delivery = {
                "status": delivery["action"], "packNumber": delivery["packNumber"], "packEventId": delivery["packEventId"],
                "issuedAt": delivery["issuedAt"], "deliveredAt": delivery["createdAt"] if delivery["action"] == "Delivered" else "",
                "recipient": delivery["recipientName"], "channel": delivery["channel"],
            }
        if summary_only:
            preview = document_preview_fragment(company=request.company, membership=request.company_membership, document_id=row.id)
            invoice = preview.get("invoice") or {}
            attachment = (invoice.get("attachment") or {}) if isinstance(invoice, dict) else {}
            if isinstance(invoice, dict) and "attachment" in invoice:
                preview["invoice"] = {key: value for key, value in invoice.items() if key != "attachment"}
            payload = serialize_document(
                row,
                include_snapshot=False,
                delivery=delivery,
                verify_integrity=False,
                document_variant=str(preview.get("documentVariant") or ""),
                attachment=attachment,
            )
            payload["preview"] = preview
            payload["previewMode"] = "summary"
        else:
            payload = serialize_document(row, include_snapshot=True, delivery=delivery)
            payload["previewMode"] = "full"
        payload["deliveryHistory"] = history
        return JsonResponse({"ok": True, "document": payload})
    except Exception as exc:
        return _errors(exc)

