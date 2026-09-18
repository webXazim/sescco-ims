from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import branch_scope_ids, membership_has_permission, project_scope_ids

from ..models import BusinessDocument, DocumentType, DocumentWorkspace, production_document_label
from apps.internal_payroll.models import PayrollRunLine, SalaryPaymentRow
from apps.core.models import AuditArea, AuditEvent
from apps.rental_manpower.models import RentalTimesheetPeriod, SupplierPayment, SupplierPaymentAllocation, SupplierSettlement
from ..services import verify_document_snapshot


DOCUMENT_PAGE_SIZES = {25, 50, 100}


def _page_number(value: object) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _page_size(value: object) -> int:
    try:
        size = int(value or 50)
    except (TypeError, ValueError):
        size = 50
    return size if size in DOCUMENT_PAGE_SIZES else 50



def _scope_documents(qs, *, company, membership):
    """Apply Branch/Project scope to immutable document history.

    Whole-company Internal Timesheet documents are intentionally unavailable to a
    branch-restricted membership because the snapshot contains employees outside that branch.
    Supplier payment receipts are visible only when *every* allocation belongs to an
    allowed project; mixed-project receipts fail closed instead of being partially redacted.
    """
    branch_ids = branch_scope_ids(membership)
    project_ids = project_scope_ids(membership)
    allowed = Q()

    if branch_ids is None:
        allowed |= Q(workspace=DocumentWorkspace.INTERNAL)
    elif branch_ids:
        salary_ids = PayrollRunLine.objects.for_company(company).filter(branch_id_snapshot__in=branch_ids).values("pk")
        receipt_ids = SalaryPaymentRow.objects.for_company(company).filter(run_line__branch_id_snapshot__in=branch_ids).values("pk")
        allowed |= Q(document_type=DocumentType.SALARY_SLIP, source_id__in=salary_ids)
        allowed |= Q(document_type=DocumentType.SALARY_PAYMENT_RECEIPT, source_id__in=receipt_ids)

    if project_ids is None:
        allowed |= Q(workspace=DocumentWorkspace.RENTAL)
    elif project_ids:
        timesheet_ids = RentalTimesheetPeriod.objects.for_company(company).filter(project_id__in=project_ids).values("pk")
        settlement_ids = SupplierSettlement.objects.for_company(company).filter(project_id__in=project_ids).values("pk")
        outside_allocations = SupplierPaymentAllocation.objects.for_company(company).filter(payment_id=OuterRef("pk")).exclude(settlement__project_id__in=project_ids)
        payment_ids = (
            SupplierPayment.objects.for_company(company)
            .annotate(_outside_scope=Exists(outside_allocations))
            .filter(_outside_scope=False, allocations__settlement__project_id__in=project_ids)
            .values("pk")
        )
        allowed |= Q(document_type=DocumentType.RENTAL_TIMESHEET, source_id__in=timesheet_ids)
        allowed |= Q(document_type__in=[DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE], source_id__in=settlement_ids)
        allowed |= Q(document_type=DocumentType.SUPPLIER_PAYMENT_RECEIPT, source_id__in=payment_ids)

    return qs.filter(allowed) if allowed else qs.none()

def documents_for_company(*, company, membership, workspace: str = "", query: str = "", period_start=None, document_type: str = "", entity_reference: str = ""):
    qs = BusinessDocument.objects.for_company(company).select_related("finalized_by")
    allowed = []
    if membership_has_permission(membership, AccessPermission.INTERNAL_DOCUMENTS_VIEW) or membership_has_permission(membership, AccessPermission.SHARED_DOCUMENTS_VIEW):
        allowed.append(DocumentWorkspace.INTERNAL)
    if membership_has_permission(membership, AccessPermission.RENTAL_DOCUMENTS_VIEW) or membership_has_permission(membership, AccessPermission.SHARED_DOCUMENTS_VIEW):
        allowed.append(DocumentWorkspace.RENTAL)
    qs = qs.filter(workspace__in=allowed)
    qs = _scope_documents(qs, company=company, membership=membership)
    if workspace:
        qs = qs.filter(workspace=workspace)
    if period_start:
        qs = qs.filter(period_start=period_start)
    if document_type:
        if document_type == "supplier_timesheet":
            qs = qs.filter(document_type=DocumentType.RENTAL_TIMESHEET, snapshot__document_variant="supplier_timesheet")
        elif document_type == DocumentType.RENTAL_TIMESHEET:
            qs = qs.filter(document_type=DocumentType.RENTAL_TIMESHEET).filter(
                Q(snapshot__document_variant__isnull=True) | Q(snapshot__document_variant="") | Q(snapshot__document_variant="project_timesheet")
            )
        else:
            qs = qs.filter(document_type=document_type)
    if entity_reference:
        qs = qs.filter(entity_reference__iexact=entity_reference.strip())
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


def serialize_document(document: BusinessDocument, *, include_snapshot: bool = False, delivery: dict[str, object] | None = None) -> dict[str, object]:
    variant = str(((document.snapshot or {}).get("document_variant") or "")).strip()
    if document.document_type == DocumentType.RENTAL_TIMESHEET:
        type_label = "Supplier Timesheet Statement" if variant == "supplier_timesheet" else "Project Timesheet"
    else:
        type_label = production_document_label(document.document_type)
    data: dict[str, object] = {
        "id": str(document.id),
        "workspace": document.workspace,
        "type": document.document_type,
        "documentVariant": variant,
        "typeLabel": type_label,
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
        "delivery": delivery or {"status": "Not issued", "packNumber": "", "packEventId": "", "issuedAt": "", "deliveredAt": ""},
    }
    attachment = (((document.snapshot or {}).get("invoice") or {}).get("attachment") or {})
    if attachment.get("storage_key"):
        data["sourceAttachmentUrl"] = reverse("documents:document-source-attachment", kwargs={"document_id": document.id})
        data["sourceAttachmentName"] = attachment.get("original_name") or "Supplier invoice"
    else:
        data["sourceAttachmentUrl"] = ""
        data["sourceAttachmentName"] = ""
    if include_snapshot:
        data["snapshot"] = document.snapshot
    return data


def document_page_context(
    *, company, membership, workspace: str, query: str = "", period_start=None,
    document_type: str = "", entity_reference: str = "", page: object = 1, page_size: object = 50,
) -> dict[str, object]:
    """Return one bounded document page plus exact workspace-wide counts/filter metadata."""
    base = documents_for_company(company=company, membership=membership, workspace=workspace)
    filtered = documents_for_company(
        company=company,
        membership=membership,
        workspace=workspace,
        query=query,
        period_start=period_start,
        document_type=document_type,
        entity_reference=entity_reference,
    )
    size = _page_size(page_size)
    paginator = Paginator(filtered, size)
    page_obj = paginator.get_page(_page_number(page))
    type_counts = {
        row["document_type"]: row["count"]
        for row in base.values("document_type").annotate(count=Count("id")).order_by()
    }
    supplier_timesheet_count = base.filter(
        document_type=DocumentType.RENTAL_TIMESHEET, snapshot__document_variant="supplier_timesheet"
    ).count()
    if supplier_timesheet_count:
        type_counts["supplier_timesheet"] = supplier_timesheet_count
        type_counts[DocumentType.RENTAL_TIMESHEET] = max(0, int(type_counts.get(DocumentType.RENTAL_TIMESHEET, 0)) - supplier_timesheet_count)
    periods = [
        value.strftime("%Y-%m")
        for value in base.exclude(period_start__isnull=True)
        .values_list("period_start", flat=True)
        .distinct()
        .order_by("-period_start")
    ]
    page_documents = list(page_obj.object_list)
    delivery_by_document: dict[str, dict[str, object]] = {}
    page_ids = [str(item.id) for item in page_documents]
    if page_ids:
        delivery_events = (
            AuditEvent.objects.filter(
                company=company, area=AuditArea.DOCUMENTS, object_type="documents.BusinessDocument",
                object_id__in=page_ids, action__in=["documents.delivery_prepared", "documents.delivery_sent", "documents.delivery_opened", "documents.delivery_delivered"],
            )
            .order_by("-created_at", "-id")
        )
        for event in delivery_events:
            if event.object_id in delivery_by_document:
                continue
            metadata = event.metadata or {}
            delivered = event.action == "documents.delivery_delivered"
            opened = event.action == "documents.delivery_opened"
            sent = event.action == "documents.delivery_sent"
            delivery_by_document[event.object_id] = {
                "status": "Delivered" if delivered else ("Opened" if opened else ("Sent" if sent else "Prepared")),
                "packNumber": metadata.get("pack_number", ""),
                "packEventId": metadata.get("pack_event_id", ""),
                "issuedAt": metadata.get("issued_at", ""),
                "deliveredAt": event.created_at.isoformat() if delivered else "",
                "recipient": metadata.get("recipient_name", ""),
                "channel": metadata.get("channel", ""),
            }
    return {
        "surface": "documents_page",
        "documents": [serialize_document(item, delivery=delivery_by_document.get(str(item.id))) for item in page_documents],
        "summary": {"count": base.count(), "typeCounts": type_counts},
        "filters": {"periods": periods, "statuses": ["Final"]},
        "meta": {
            "count": paginator.count,
            "page": page_obj.number,
            "pageSize": size,
            "totalPages": paginator.num_pages,
            "rangeStart": page_obj.start_index() if paginator.count else 0,
            "rangeEnd": page_obj.end_index() if paginator.count else 0,
        },
    }


def document_context(*, company, membership, workspace: str = "") -> dict[str, object]:
    # Upgrade 1.0.76: document lists are deferred to the paginated API. Keeping the
    # shell empty prevents Payroll bootstrap cost from growing with document history.
    return {"documents": [], "deferred": True}
