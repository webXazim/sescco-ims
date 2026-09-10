from __future__ import annotations

from django.db.models import Q

from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace

from ..models import BusinessDocument, DocumentWorkspace
from ..services import verify_document_snapshot


def documents_for_company(*, company, membership, workspace: str = "", query: str = "", period_start=None, document_type: str = ""):
    qs = BusinessDocument.objects.for_company(company).select_related("finalized_by")
    allowed = []
    if membership_can_workspace(membership, Workspace.INTERNAL):
        allowed.append(DocumentWorkspace.INTERNAL)
    if membership_can_workspace(membership, Workspace.RENTAL):
        allowed.append(DocumentWorkspace.RENTAL)
    qs = qs.filter(workspace__in=allowed)
    if workspace:
        qs = qs.filter(workspace=workspace)
    if period_start:
        qs = qs.filter(period_start=period_start)
    if document_type:
        qs = qs.filter(document_type=document_type)
    q = query.strip()
    if q:
        qs = qs.filter(
            Q(document_number__icontains=q)
            | Q(title__icontains=q)
            | Q(entity_reference__icontains=q)
            | Q(entity_name__icontains=q)
            | Q(source_reference__icontains=q)
            | Q(external_reference__icontains=q)
        )
    return qs


def serialize_document(document: BusinessDocument, *, include_snapshot: bool = False) -> dict[str, object]:
    data: dict[str, object] = {
        "id": str(document.id),
        "workspace": document.workspace,
        "type": document.document_type,
        "typeLabel": document.get_document_type_display(),
        "number": document.document_number,
        "title": document.title,
        "status": document.get_status_display(),
        "period": document.period_start.strftime("%B %Y") if document.period_start else "",
        "periodKey": document.period_start.strftime("%Y-%m") if document.period_start else "",
        "entityReference": document.entity_reference,
        "entityName": document.entity_name,
        "sourceModel": document.source_model,
        "sourceId": str(document.source_id),
        "sourceReference": document.source_reference,
        "externalReference": document.external_reference,
        "finalizedAt": document.finalized_at.isoformat(),
        "finalizedBy": (document.finalized_by.get_full_name().strip() or document.finalized_by.username) if document.finalized_by else "System",
        "integrityOk": verify_document_snapshot(document),
    }
    if include_snapshot:
        data["snapshot"] = document.snapshot
    return data


def document_context(*, company, membership, workspace: str = "") -> dict[str, object]:
    rows = documents_for_company(company=company, membership=membership, workspace=workspace)[:250]
    return {"documents": [serialize_document(item) for item in rows]}
