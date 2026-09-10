from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
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
