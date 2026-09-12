from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from pathlib import Path
import mimetypes

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from apps.accounts.permissions import company_access_required, membership_can_workspace
from apps.accounts.roles import Workspace

from .models import BusinessDocument
from .services import verify_document_snapshot


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
def print_document_asset(request, document_id, asset_kind):
    if asset_kind not in {"logo", "letterhead", "watermark"}:
        raise Http404
    document = get_object_or_404(BusinessDocument.objects.for_company(request.company), pk=document_id)
    if not membership_can_workspace(request.company_membership, Workspace(document.workspace)):
        raise PermissionDenied("Your role cannot access this document.")
    if not verify_document_snapshot(document):
        raise PermissionDenied("Document integrity verification failed.")
    storage_name = str(((document.snapshot or {}).get("issuer") or {}).get("branding", {}).get(asset_kind) or "")
    if not storage_name or not default_storage.exists(storage_name):
        raise Http404
    content_type = mimetypes.guess_type(storage_name)[0] or "application/octet-stream"
    response = FileResponse(default_storage.open(storage_name, "rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{Path(storage_name).name}"'
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response
