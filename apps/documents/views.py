from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import company_access_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.core.models import AuditArea, AuditEvent
from apps.core.services.audit import record_audit_event

from .models import BusinessDocument, DocumentType, production_document_label
from .selectors import documents_for_company
from .services import verify_document_snapshot
from .delivery import (
    SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
    resolve_delivery_share,
    supplier_delivery_document_label,
    supplier_delivery_filename,
    supplier_delivery_is_primary,
    supplier_delivery_manifest_entry,
)
from .printing import (
    SupplierTimesheetPackWorkerNotFound,
    build_supplier_timesheet_pack_print_context,
    build_supplier_timesheet_pack_worker_print_context,
)
import hashlib




def _document_headpad_url(document) -> str:
    return static("payroll/assets/sescco-company-document-headpad-v2.png")



def _document_print_context(*, document, snapshot, headpad_url: str, shared_view: bool = False) -> dict:
    document_label = production_document_label(document.document_type)
    if document.document_type == DocumentType.RENTAL_TIMESHEET and snapshot.get("document_variant") == "supplier_timesheet":
        document_label = "Supplier Timesheet Statement"
    elif document.document_type == DocumentType.RENTAL_TIMESHEET:
        document_label = "Project Timesheet"
    suggested_file_name = supplier_delivery_filename(document) if document.workspace == "rental" else f"{document.document_number}.pdf"
    context = {
        "document": document,
        "snapshot": snapshot,
        "headpad_url": headpad_url,
        "document_label": document_label,
        "shared_view": shared_view,
        "suggested_file_name": suggested_file_name,
        "page_title": suggested_file_name.rsplit(".", 1)[0],
    }
    if document.document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        context["supplier_timesheet_pack_print"] = build_supplier_timesheet_pack_print_context(snapshot)
    return context

def _worker_timesheet_extract_context(*, document, worker_id, headpad_url: str, shared_view: bool = False, parent_print_url: str = "") -> dict:
    if document.document_type != DocumentType.SUPPLIER_TIMESHEET_PACK:
        raise Http404("Worker timesheet extracts are available only for Supplier Monthly Timesheet Packs.")
    try:
        worker_print = build_supplier_timesheet_pack_worker_print_context(document.snapshot or {}, worker_id=worker_id)
    except SupplierTimesheetPackWorkerNotFound as exc:
        raise Http404("Worker is not part of this finalized Supplier Timesheet Pack.") from exc
    worker = worker_print["worker"]
    return {
        "document": document,
        "snapshot": document.snapshot or {},
        "headpad_url": headpad_url,
        "document_label": "Worker Monthly Timesheet",
        "shared_view": shared_view,
        "worker_timesheet_extract": True,
        "supplier_timesheet_pack_print": worker_print,
        "supplier_timesheet_pack_worker": worker,
        "parent_print_url": parent_print_url,
        "page_title": f"{document.document_number} · {worker['worker_number']} · Worker Monthly Timesheet",
    }


def _private_print_response(response):
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _can_view_document(membership, document) -> bool:
    if document.workspace == "internal":
        required = AccessPermission.INTERNAL_DOCUMENTS_VIEW
    elif document.workspace == "rental":
        required = AccessPermission.RENTAL_DOCUMENTS_VIEW
    else:
        return False
    return membership_has_permission(membership, required) or membership_has_permission(membership, AccessPermission.SHARED_DOCUMENTS_VIEW)


@login_required
@company_access_required
def print_document(request, document_id):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not _can_view_document(request.company_membership, document):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    snapshot = document.snapshot or {}
    return render(
        request,
        "documents/print.html",
        _document_print_context(
            document=document,
            snapshot=snapshot,
            headpad_url=_document_headpad_url(document),
        ),
    )



@login_required
@company_access_required
def print_supplier_timesheet_worker(request, document_id, worker_id):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not _can_view_document(request.company_membership, document):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    response = render(
        request,
        "documents/print.html",
        _worker_timesheet_extract_context(
            document=document,
            worker_id=worker_id,
            headpad_url=_document_headpad_url(document),
            parent_print_url=reverse("documents:print-document", kwargs={"document_id": document.id}),
        ),
    )
    return _private_print_response(response)


def _delivery_document_entries(pack: AuditEvent, documents: list[BusinessDocument]) -> list[dict[str, object]]:
    metadata = pack.metadata or {}
    frozen_manifest = {
        str(row.get("id")): row
        for row in (metadata.get("document_manifest") or [])
        if isinstance(row, dict) and row.get("id")
    }
    entries = []
    for document in documents:
        manifest = frozen_manifest.get(str(document.id)) or supplier_delivery_manifest_entry(document)
        entries.append({
            "document": document,
            "role": manifest.get("role") or "",
            "label": manifest.get("label") or supplier_delivery_document_label(document),
            "file_name": manifest.get("file_name") or supplier_delivery_filename(document),
            "primary": bool(manifest.get("primary")) or supplier_delivery_is_primary(document),
        })
    return entries


@login_required
@company_access_required
def print_delivery_pack(request, pack_event_id):
    if not (membership_has_permission(request.company_membership, AccessPermission.RENTAL_DOCUMENTS_VIEW) or membership_has_permission(request.company_membership, AccessPermission.SHARED_DOCUMENTS_VIEW)):
        raise PermissionDenied("Your role cannot access Rental Manpower documents.")
    pack = get_object_or_404(
        AuditEvent.objects.filter(company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued", object_type="documents.DocumentDeliveryPack"),
        pk=pack_event_id,
    )
    metadata = pack.metadata or {}
    raw_ids = metadata.get("document_ids", [])
    documents = list(
        documents_for_company(company=request.company, membership=request.company_membership, workspace="rental")
        .filter(pk__in=raw_ids).order_by("period_start", "document_type", "document_number")
    )
    if len(documents) != len(raw_ids):
        raise PermissionDenied("One or more issue-pack documents are outside your current document scope.")
    if any(not verify_document_snapshot(document) for document in documents):
        raise PermissionDenied("Document integrity verification failed.")
    delivered = AuditEvent.objects.filter(
        company=request.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
        object_type="documents.DocumentDeliveryPack", object_id=pack.object_id,
    ).order_by("-created_at").first()
    return render(request, "documents/delivery_pack.html", {
        "pack": pack,
        "metadata": metadata,
        "documents": documents,
        "document_entries": _delivery_document_entries(pack, documents),
        "delivered": delivered,
        "headpad_url": static("payroll/assets/sescco-company-document-headpad-v2.png"),
    })


def _share_documents(pack: AuditEvent) -> list[BusinessDocument]:
    metadata = pack.metadata or {}
    raw_ids = metadata.get("document_ids", [])
    documents = list(
        BusinessDocument.objects.for_company(pack.company)
        .filter(pk__in=raw_ids)
        .select_related("finalized_by")
        .order_by("period_start", "document_type", "document_number")
    )
    if len(documents) != len(raw_ids):
        raise PermissionDenied("This document pack is unavailable.")
    if any(not verify_document_snapshot(document) for document in documents):
        raise PermissionDenied("Document integrity verification failed.")
    return documents


def _share_delivered_event(pack: AuditEvent):
    return AuditEvent.objects.filter(
        company=pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
        object_type="documents.DocumentDeliveryPack", object_id=pack.object_id,
    ).order_by("-created_at", "-id").first()


def _record_share_opened(*, request, pack: AuditEvent, documents: list[BusinessDocument]) -> AuditEvent | None:
    # Serialize the first-open transition on the immutable pack event. Two simultaneous
    # supplier requests must not create duplicate Opened evidence for the same pack.
    with transaction.atomic():
        locked_pack = AuditEvent.objects.select_for_update().get(pk=pack.pk)
        existing = AuditEvent.objects.filter(
            company=locked_pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_opened",
            object_type="documents.DocumentDeliveryPack", object_id=locked_pack.object_id,
        ).order_by("-created_at", "-id").first()
        if existing is not None:
            return existing
        metadata = locked_pack.metadata or {}
        opened = record_audit_event(
            company=locked_pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_opened",
            object_type="documents.DocumentDeliveryPack", object_id=locked_pack.object_id, object_label=locked_pack.object_label,
            request=request, metadata={"issue_event_id": str(locked_pack.id), "opened_at": timezone.now().isoformat()},
        )
        for document in documents:
            record_audit_event(
                company=locked_pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_opened",
                object_type="documents.BusinessDocument", object_id=document.id, object_label=document.document_number,
                request=request, metadata={
                    "pack_event_id": str(locked_pack.id), "pack_number": locked_pack.object_label,
                    "supplier_code": metadata.get("supplier_code", ""),
                    "recipient_name": metadata.get("recipient_name", ""),
                    "recipient_email": metadata.get("recipient_email", ""),
                    "recipient_phone": metadata.get("recipient_phone", ""),
                    "channel": metadata.get("channel", ""), "reference": metadata.get("reference", ""),
                    "note": metadata.get("note", ""), "issued_at": metadata.get("issued_at", ""),
                    "opened_event_id": str(opened.id), "delivery_source": "supplier_share",
                },
            )
        return opened


def delivery_pack_share(request, pack_event_id, token):
    share = resolve_delivery_share(pack_event_id=pack_event_id, token=token)
    pack = share.pack
    documents = _share_documents(pack)
    _record_share_opened(request=request, pack=pack, documents=documents)
    response = render(request, "documents/delivery_share.html", {
        "pack": pack, "metadata": pack.metadata or {}, "documents": documents,
        "document_entries": _delivery_document_entries(pack, documents),
        "delivered": _share_delivered_event(pack), "token": token, "expires_at": share.expires_at,
        "headpad_url": static("payroll/assets/sescco-company-document-headpad-v2.png"),
    })
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
def delivery_pack_share_acknowledge(request, pack_event_id, token):
    share = resolve_delivery_share(pack_event_id=pack_event_id, token=token)
    pack = share.pack
    documents = _share_documents(pack)
    # Direct acknowledgement still records Opened first, and the pack row serializes the
    # Delivered transition so repeated/concurrent acknowledgements stay idempotent.
    _record_share_opened(request=request, pack=pack, documents=documents)
    with transaction.atomic():
        locked_pack = AuditEvent.objects.select_for_update().get(pk=pack.pk)
        existing = _share_delivered_event(locked_pack)
        if existing is None:
            metadata = locked_pack.metadata or {}
            delivered_event = record_audit_event(
                company=locked_pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
                object_type="documents.DocumentDeliveryPack", object_id=locked_pack.object_id, object_label=locked_pack.object_label,
                request=request, metadata={
                    "issue_event_id": str(locked_pack.id), "reference": "Supplier acknowledgement", "note": "",
                    "acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
                },
            )
            for document in documents:
                record_audit_event(
                    company=locked_pack.company, area=AuditArea.DOCUMENTS, action="documents.delivery_delivered",
                    object_type="documents.BusinessDocument", object_id=document.id, object_label=document.document_number,
                    request=request, metadata={
                        "pack_event_id": str(locked_pack.id), "pack_number": locked_pack.object_label,
                        "supplier_code": metadata.get("supplier_code", ""),
                        "recipient_name": metadata.get("recipient_name", ""),
                        "recipient_email": metadata.get("recipient_email", ""),
                        "recipient_phone": metadata.get("recipient_phone", ""),
                        "channel": metadata.get("channel", ""), "reference": "Supplier acknowledgement",
                        "note": "", "issued_at": metadata.get("issued_at", ""),
                        "delivered_event_id": str(delivered_event.id), "delivery_source": "supplier_share",
                        "acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
                    },
                )
    return redirect("documents:delivery-pack-share", pack_event_id=pack_event_id, token=token)


def delivery_pack_shared_document_print(request, pack_event_id, token, document_id):
    share = resolve_delivery_share(pack_event_id=pack_event_id, token=token)
    pack = share.pack
    documents = _share_documents(pack)
    document = next((row for row in documents if row.id == document_id), None)
    if document is None:
        raise PermissionDenied("This document is not part of the supplier issue pack.")
    snapshot = document.snapshot or {}
    response = render(
        request,
        "documents/print.html",
        _document_print_context(
            document=document,
            snapshot=snapshot,
            headpad_url=static("payroll/assets/sescco-company-document-headpad-v2.png"),
            shared_view=True,
        ),
    )
    return _private_print_response(response)


def delivery_pack_shared_worker_print(request, pack_event_id, token, document_id, worker_id):
    share = resolve_delivery_share(pack_event_id=pack_event_id, token=token)
    pack = share.pack
    documents = _share_documents(pack)
    document = next((row for row in documents if row.id == document_id), None)
    if document is None:
        raise PermissionDenied("This document is not part of the supplier issue pack.")
    response = render(
        request,
        "documents/print.html",
        _worker_timesheet_extract_context(
            document=document,
            worker_id=worker_id,
            headpad_url=static("payroll/assets/sescco-company-document-headpad-v2.png"),
            shared_view=True,
            parent_print_url=reverse(
                "documents:delivery-pack-shared-document-print",
                kwargs={"pack_event_id": pack_event_id, "token": token, "document_id": document.id},
            ),
        ),
    )
    return _private_print_response(response)


@login_required
@company_access_required
def document_brand_asset(request, document_id, kind: str):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not _can_view_document(request.company_membership, document):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    if kind not in {"logo", "letterhead", "watermark"}:
        raise Http404("Unknown branding asset.")
    descriptor = (((document.snapshot or {}).get("issuer") or {}).get("branding") or {}).get(kind)
    if not descriptor:
        raise Http404("Branding asset is not part of this document snapshot.")
    try:
        if descriptor.get("storage_key"):
            handle = default_storage.open(descriptor["storage_key"], "rb")
        elif descriptor.get("package_path"):
            package_root = (Path(settings.BASE_DIR) / "apps" / "documents" / "assets").resolve()
            asset_path = (Path(settings.BASE_DIR) / descriptor["package_path"]).resolve()
            if package_root != asset_path.parent or not asset_path.is_file():
                raise Http404("Historical packaged branding asset is unavailable.")
            handle = asset_path.open("rb")
        else:
            raise Http404("Branding asset is not part of this document snapshot.")
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        handle.seek(0)
    except (FileNotFoundError, OSError):
        raise Http404("Historical branding asset is unavailable.")
    if digest.hexdigest() != descriptor.get("sha256"):
        handle.close()
        raise PermissionDenied("Historical branding asset integrity verification failed.")
    response = FileResponse(handle, content_type=descriptor.get("content_type") or "application/octet-stream")
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@company_access_required
def document_source_attachment(request, document_id):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not _can_view_document(request.company_membership, document):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    descriptor = (((document.snapshot or {}).get("invoice") or {}).get("attachment") or {})
    storage_key = descriptor.get("storage_key")
    if not storage_key:
        raise Http404("Supplier invoice attachment is not available.")
    try:
        handle = default_storage.open(storage_key, "rb")
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        handle.seek(0)
    except (FileNotFoundError, OSError):
        raise Http404("Supplier invoice attachment is unavailable.")
    if digest.hexdigest() != descriptor.get("sha256"):
        handle.close()
        raise PermissionDenied("Supplier invoice attachment integrity verification failed.")
    response = FileResponse(handle, content_type=descriptor.get("content_type") or "application/octet-stream")
    filename = Path(str(descriptor.get("original_name") or "supplier-invoice")).name.replace('"', '')
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response
