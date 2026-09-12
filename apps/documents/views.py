from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from apps.accounts.permissions import company_access_required, membership_can_workspace
from apps.accounts.roles import Workspace

from .models import BusinessDocument
from .services import verify_document_snapshot
import hashlib


@login_required
@company_access_required
def print_document(request, document_id):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not membership_can_workspace(request.company_membership, Workspace(document.workspace)):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    return render(request, "documents/print.html", {"document": document, "snapshot": document.snapshot})


@login_required
@company_access_required
def document_brand_asset(request, document_id, kind: str):
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not membership_can_workspace(request.company_membership, Workspace(document.workspace)):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    if kind not in {"logo", "letterhead", "watermark"}:
        raise Http404("Unknown branding asset.")
    descriptor = (((document.snapshot or {}).get("issuer") or {}).get("branding") or {}).get(kind)
    if not descriptor or not descriptor.get("storage_key"):
        raise Http404("Branding asset is not part of this document snapshot.")
    storage_key = descriptor["storage_key"]
    try:
        handle = default_storage.open(storage_key, "rb")
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
