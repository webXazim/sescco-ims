from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.accounts.permissions import company_access_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission

from .models import BusinessDocument, production_document_label
from .services import verify_document_snapshot
import hashlib




def _document_headpad_url(document) -> str:
    return static("payroll/assets/sescco-company-document-headpad-v2.png")

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
@xframe_options_sameorigin
def print_document(request, document_id):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not _can_view_document(request.company_membership, document):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    return render(request, "documents/print.html", {
        "document": document,
        "snapshot": document.snapshot,
        "headpad_url": _document_headpad_url(document),
        "document_label": production_document_label(document.document_type),
        "embed": request.GET.get("embed") == "1",
    })


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
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
