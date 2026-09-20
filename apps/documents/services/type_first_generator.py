from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count, Exists, OuterRef, Q, Sum

from apps.accounts.access_policy import project_scope_ids
from apps.rental_manpower.models import (
    RentalSettlementStatus,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierPaymentStatus,
    SupplierSettlement,
)

from ..models import BusinessDocument, DocumentType, production_document_label


TYPE_FIRST_RENTAL_DOCUMENT_TYPES = (
    DocumentType.SUPPLIER_TIMESHEET_PACK,
    DocumentType.SUPPLIER_SETTLEMENT,
    DocumentType.SUPPLIER_INVOICE,
    DocumentType.SUPPLIER_PAYMENT_RECEIPT,
)
TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE = 25
_FINAL_SETTLEMENT_STATUSES = (
    RentalSettlementStatus.APPROVED,
    RentalSettlementStatus.PAYMENT_PROCESSING,
    RentalSettlementStatus.PARTIALLY_PAID,
    RentalSettlementStatus.PAID,
    RentalSettlementStatus.CLOSED,
)

_TYPE_META = {
    DocumentType.SUPPLIER_TIMESHEET_PACK: {
        "key": DocumentType.SUPPLIER_TIMESHEET_PACK,
        "label": "Supplier Timesheet",
        "description": "Monthly supplier/project pack with a worker summary and one monthly sheet per worker.",
        "supplierRequired": True,
        "projectRequired": True,
        "sourceRequired": True,
        "sourceLabel": "Locked project timesheet",
        "creationMode": "json",
    },
    DocumentType.SUPPLIER_SETTLEMENT: {
        "key": DocumentType.SUPPLIER_SETTLEMENT,
        "label": production_document_label(DocumentType.SUPPLIER_SETTLEMENT),
        "description": "Approved supplier/project financial reconciliation for the selected month.",
        "supplierRequired": True,
        "projectRequired": True,
        "sourceRequired": True,
        "sourceLabel": "Approved settlement",
        "creationMode": "json",
    },
    DocumentType.SUPPLIER_INVOICE: {
        "key": DocumentType.SUPPLIER_INVOICE,
        "label": production_document_label(DocumentType.SUPPLIER_INVOICE),
        "description": "Record the supplier invoice received against an approved supplier settlement.",
        "supplierRequired": True,
        "projectRequired": True,
        "sourceRequired": True,
        "sourceLabel": "Approved settlement",
        "creationMode": "multipart",
        "requiresInvoiceAttachment": True,
    },
    DocumentType.SUPPLIER_PAYMENT_RECEIPT: {
        "key": DocumentType.SUPPLIER_PAYMENT_RECEIPT,
        "label": production_document_label(DocumentType.SUPPLIER_PAYMENT_RECEIPT),
        "description": "Supplier-facing advice for a completed supplier payment.",
        "supplierRequired": True,
        "projectRequired": False,
        "sourceRequired": True,
        "sourceLabel": "Paid supplier payment",
        "creationMode": "json",
    },
}


def type_first_generator_catalog() -> list[dict[str, Any]]:
    """Static purpose-first catalog. It intentionally performs no source queries."""
    return [dict(_TYPE_META[item]) for item in TYPE_FIRST_RENTAL_DOCUMENT_TYPES]


def normalize_type_first_document_type(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized not in TYPE_FIRST_RENTAL_DOCUMENT_TYPES:
        raise ValidationError({"document_type": "Choose a supported supplier document type."})
    return normalized


def type_first_meta(document_type: str) -> dict[str, Any]:
    return dict(_TYPE_META[normalize_type_first_document_type(document_type)])


def selector_page(value: object, page_size: object) -> tuple[int, int]:
    try:
        normalized_page = max(1, int(value or 1))
    except (TypeError, ValueError):
        normalized_page = 1
    try:
        normalized_size = max(1, min(TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE, int(page_size or 10)))
    except (TypeError, ValueError):
        normalized_size = 10
    return normalized_page, normalized_size


def _bounded_rows(qs, *, page: int, page_size: int) -> tuple[list[Any], bool]:
    start = (page - 1) * page_size
    raw = list(qs[start : start + page_size + 1])
    return raw[:page_size], len(raw) > page_size


def _scope_queryset(qs, membership, field: str):
    allowed = project_scope_ids(membership)
    if allowed is None:
        return qs
    return qs.filter(**{f"{field}__in": allowed}) if allowed else qs.none()


def _timesheet_entries(*, company, membership, period_start):
    qs = RentalTimesheetEntry.objects.for_company(company).filter(
        period__period_start=period_start,
        period__status=RentalTimesheetStatus.LOCKED,
    )
    return _scope_queryset(qs, membership, "period__project_id")


def _settlements(*, company, membership, period_start):
    qs = SupplierSettlement.objects.for_company(company).filter(
        period_start=period_start,
        status__in=_FINAL_SETTLEMENT_STATUSES,
    )
    return _scope_queryset(qs, membership, "project_id")


def _payments(*, company, membership, period_start):
    qs = SupplierPayment.objects.for_company(company).filter(
        status=SupplierPaymentStatus.PAID,
        allocations__settlement__period_start=period_start,
    )
    allowed = project_scope_ids(membership)
    if allowed is not None:
        if not allowed:
            return qs.none()
        outside = SupplierPaymentAllocation.objects.for_company(company).filter(
            payment_id=OuterRef("pk")
        ).exclude(settlement__project_id__in=allowed)
        qs = qs.annotate(_outside_scope=Exists(outside)).filter(_outside_scope=False)
    return qs.distinct()


def eligible_suppliers(*, company, membership, document_type: str, period_start, query: str = "", page: int = 1, page_size: int = 10) -> dict[str, Any]:
    document_type = normalize_type_first_document_type(document_type)
    q = str(query or "").strip()
    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        qs = _timesheet_entries(company=company, membership=membership, period_start=period_start)
    elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        qs = _settlements(company=company, membership=membership, period_start=period_start)
    else:
        qs = _payments(company=company, membership=membership, period_start=period_start)
    if q:
        qs = qs.filter(Q(supplier_code__icontains=q) | Q(supplier_name__icontains=q))
    rows, has_next = _bounded_rows(
        qs.values("supplier_code", "supplier_name").distinct().order_by("supplier_code", "supplier_name"),
        page=page,
        page_size=page_size,
    )
    return {
        "results": [
            {"code": row["supplier_code"], "name": row["supplier_name"], "label": f"{row['supplier_code']} · {row['supplier_name']}"}
            for row in rows
        ],
        "hasNext": has_next,
    }


def eligible_projects(*, company, membership, document_type: str, period_start, supplier_code: str, query: str = "", page: int = 1, page_size: int = 10) -> dict[str, Any]:
    document_type = normalize_type_first_document_type(document_type)
    supplier = str(supplier_code or "").strip().upper()
    if not supplier:
        raise ValidationError({"supplier_code": "Choose a supplier before searching projects."})
    q = str(query or "").strip()
    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        qs = _timesheet_entries(company=company, membership=membership, period_start=period_start).filter(supplier_code__iexact=supplier)
        if q:
            qs = qs.filter(Q(project_code__icontains=q) | Q(project_name__icontains=q))
        values = qs.values("period__project_id", "project_code", "project_name").distinct().order_by("project_code", "project_name")
        rows, has_next = _bounded_rows(values, page=page, page_size=page_size)
        results = [{"id": str(row["period__project_id"]), "code": row["project_code"], "name": row["project_name"], "label": f"{row['project_code']} · {row['project_name']}"} for row in rows]
    elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        qs = _settlements(company=company, membership=membership, period_start=period_start).filter(supplier_code__iexact=supplier)
        if q:
            qs = qs.filter(Q(project_code__icontains=q) | Q(project_name__icontains=q))
        values = qs.values("project_id", "project_code", "project_name").distinct().order_by("project_code", "project_name")
        rows, has_next = _bounded_rows(values, page=page, page_size=page_size)
        results = [{"id": str(row["project_id"]), "code": row["project_code"], "name": row["project_name"], "label": f"{row['project_code']} · {row['project_name']}"} for row in rows]
    else:
        qs = SupplierPaymentAllocation.objects.for_company(company).filter(
            payment_id__in=_payments(company=company, membership=membership, period_start=period_start).values("pk"),
            payment__supplier_code__iexact=supplier,
            settlement__period_start=period_start,
        )
        if q:
            qs = qs.filter(Q(settlement__project_code__icontains=q) | Q(settlement__project_name__icontains=q))
        values = qs.values("settlement__project_id", "settlement__project_code", "settlement__project_name").distinct().order_by("settlement__project_code", "settlement__project_name")
        rows, has_next = _bounded_rows(values, page=page, page_size=page_size)
        results = [{"id": str(row["settlement__project_id"]), "code": row["settlement__project_code"], "name": row["settlement__project_name"], "label": f"{row['settlement__project_code']} · {row['settlement__project_name']}"} for row in rows]
    return {"results": results, "hasNext": has_next}


def _existing_for_source(*, company, document_type: str, source, supplier_code: str = ""):
    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{str(supplier_code).upper()}"
    else:
        source_model = source._meta.label_lower
    return BusinessDocument.objects.for_company(company).filter(
        document_type=document_type,
        source_model=source_model,
        source_id=source.pk,
    ).first()


def _serialize_existing(document) -> dict[str, Any] | None:
    if document is None:
        return None
    return {
        "id": str(document.pk),
        "number": document.document_number,
        "title": document.title,
        "finalizedAt": document.finalized_at.isoformat(),
    }


def _source_queryset(*, company, membership, document_type: str, period_start, supplier_code: str, project_id: str = ""):
    supplier = str(supplier_code or "").strip().upper()
    if not supplier:
        raise ValidationError({"supplier_code": "Supplier is required."})
    meta = type_first_meta(document_type)
    if meta.get("projectRequired") and not str(project_id or "").strip():
        raise ValidationError({"project_id": "Project is required for this document type."})

    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        entry_scope = _timesheet_entries(company=company, membership=membership, period_start=period_start).filter(supplier_code__iexact=supplier)
        if project_id:
            entry_scope = entry_scope.filter(period__project_id=project_id)
        has_rows = entry_scope.filter(period_id=OuterRef("pk"))
        qs = RentalTimesheetPeriod.objects.for_company(company).filter(
            period_start=period_start,
            status=RentalTimesheetStatus.LOCKED,
        )
        qs = _scope_queryset(qs, membership, "project_id").annotate(_has_supplier=Exists(has_rows)).filter(_has_supplier=True)
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs.select_related("project").order_by("project__code"), supplier

    if document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        qs = _settlements(company=company, membership=membership, period_start=period_start).filter(supplier_code__iexact=supplier)
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs.select_related("project", "supplier").order_by("project_code"), supplier

    qs = _payments(company=company, membership=membership, period_start=period_start).filter(supplier_code__iexact=supplier)
    if project_id:
        qs = qs.filter(allocations__settlement__period_start=period_start, allocations__settlement__project_id=project_id).distinct()
    return qs.order_by("payment_number"), supplier


def eligible_sources(*, company, membership, document_type: str, period_start, supplier_code: str, project_id: str = "", query: str = "", page: int = 1, page_size: int = 10) -> dict[str, Any]:
    document_type = normalize_type_first_document_type(document_type)
    qs, supplier = _source_queryset(
        company=company,
        membership=membership,
        document_type=document_type,
        period_start=period_start,
        supplier_code=supplier_code,
        project_id=project_id,
    )
    q = str(query or "").strip()
    if q:
        if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
            qs = qs.filter(Q(project__code__icontains=q) | Q(project__name__icontains=q))
        elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
            qs = qs.filter(Q(settlement_number__icontains=q) | Q(project_code__icontains=q) | Q(project_name__icontains=q))
        else:
            qs = qs.filter(Q(payment_number__icontains=q) | Q(transaction_reference__icontains=q))
    rows, has_next = _bounded_rows(qs, page=page, page_size=page_size)
    source_ids = [row.pk for row in rows]
    existing_by_source: dict[str, BusinessDocument] = {}
    if source_ids:
        if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
            source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{supplier}"
        else:
            source_model = rows[0]._meta.label_lower
        existing_rows = BusinessDocument.objects.for_company(company).filter(
            document_type=document_type, source_model=source_model, source_id__in=source_ids
        ).order_by("source_id", "-finalized_at")
        for document in existing_rows:
            existing_by_source.setdefault(str(document.source_id), document)

    results: list[dict[str, Any]] = []
    for row in rows:
        existing = existing_by_source.get(str(row.pk))
        if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
            label = f"{row.project.code} · {row.project.name} · Locked R{row.revision}"
            status = "Locked"
            reference = f"{row.project.code} · {period_start:%Y-%m} · R{row.revision}"
        elif document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
            label = f"{row.settlement_number} · {row.project_name}"
            status = row.get_status_display()
            reference = row.settlement_number
        else:
            label = f"{row.payment_number} · {row.get_method_display()}"
            status = row.get_status_display()
            reference = row.payment_number
        results.append({
            "sourceId": str(row.pk),
            "label": label,
            "status": status,
            "reference": reference,
            "existing": _serialize_existing(existing),
        })
    return {"results": results, "hasNext": has_next}


def resolve_type_first_source(*, company, membership, document_type: str, period_start, supplier_code: str, project_id: str = "", source_id: object):
    document_type = normalize_type_first_document_type(document_type)
    if not source_id:
        raise ValidationError({"source_id": "Choose an eligible source record."})
    qs, supplier = _source_queryset(
        company=company,
        membership=membership,
        document_type=document_type,
        period_start=period_start,
        supplier_code=supplier_code,
        project_id=project_id,
    )
    try:
        source = qs.get(pk=source_id)
    except (ObjectDoesNotExist, ValueError, TypeError) as exc:
        raise ValidationError({"source_id": "The selected source is not eligible for this supplier, project and period."}) from exc
    return source, supplier


def _hours(value: object) -> str:
    return f"{Decimal(value or 0):.2f}"


def _money(value: object) -> str:
    return f"{Decimal(value or 0):.2f}"


def review_type_first_source(*, company, membership, document_type: str, period_start, supplier_code: str, project_id: str = "", source_id: object) -> dict[str, Any]:
    source, supplier = resolve_type_first_source(
        company=company,
        membership=membership,
        document_type=document_type,
        period_start=period_start,
        supplier_code=supplier_code,
        project_id=project_id,
        source_id=source_id,
    )
    existing = _existing_for_source(company=company, document_type=document_type, source=source, supplier_code=supplier)

    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        entries = RentalTimesheetEntry.objects.for_company(company).filter(period=source, supplier_code__iexact=supplier)
        regular = entries.aggregate(worker_count=Count("worker_id", distinct=True), regular_hours=Sum("regular_hours"))
        overtime = RentalTimesheetOvertime.objects.for_company(company).filter(period=source, supplier_code__iexact=supplier).aggregate(overtime_hours=Sum("hours"))
        supplier_name = entries.values_list("supplier_name", flat=True).order_by("supplier_name").first() or supplier
        return {
            "documentType": document_type,
            "documentLabel": _TYPE_META[document_type]["label"],
            "sourceId": str(source.pk),
            "period": period_start.strftime("%Y-%m"),
            "supplier": {"code": supplier, "name": supplier_name},
            "project": {"id": str(source.project_id), "code": source.project.code, "name": source.project.name},
            "source": {"status": "Locked", "revision": source.revision},
            "summary": {
                "workerCount": int(regular.get("worker_count") or 0),
                "regularHours": _hours(regular.get("regular_hours")),
                "overtimeHours": _hours(overtime.get("overtime_hours")),
                "totalHours": _hours(Decimal(regular.get("regular_hours") or 0) + Decimal(overtime.get("overtime_hours") or 0)),
            },
            "existing": _serialize_existing(existing),
        }

    if document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        return {
            "documentType": document_type,
            "documentLabel": _TYPE_META[document_type]["label"],
            "sourceId": str(source.pk),
            "period": period_start.strftime("%Y-%m"),
            "supplier": {"code": source.supplier_code, "name": source.supplier_name},
            "project": {"id": str(source.project_id), "code": source.project_code, "name": source.project_name},
            "source": {
                "status": source.get_status_display(),
                "reference": source.settlement_number,
                "settlementRevision": source.revision,
                "timesheetRevision": source.source_timesheet_revision,
                "settlementFingerprint": source.snapshot_fingerprint,
                "timesheetPackRequired": False,
            },
            "summary": {
                "workerCount": source.worker_count,
                "regularHours": _hours(source.total_regular_hours),
                "overtimeHours": _hours(source.total_overtime_hours),
                "gross": _money(source.total_gross),
                "adjustmentEarnings": _money(source.total_adjustment_earnings),
                "adjustmentDeductions": _money(source.total_adjustment_deductions),
                "amount": _money(source.total_net),
                "matchBasis": "Approved settlement net" if document_type == DocumentType.SUPPLIER_INVOICE else "Approved settlement snapshot",
            },
            "existing": _serialize_existing(existing),
        }

    project_rows = list(
        source.allocations.filter(settlement__period_start=period_start)
        .values("settlement__project_id", "settlement__project_code", "settlement__project_name")
        .distinct().order_by("settlement__project_code")[:25]
    )
    allocation_scope = source.allocations.filter(settlement__period_start=period_start)
    allocation_summary = allocation_scope.aggregate(allocation_count=Count("pk"), allocated_total=Sum("amount"))
    return {
        "documentType": document_type,
        "documentLabel": _TYPE_META[document_type]["label"],
        "sourceId": str(source.pk),
        "period": period_start.strftime("%Y-%m"),
        "supplier": {"code": source.supplier_code, "name": source.supplier_name},
        "projects": [
            {"id": str(row["settlement__project_id"]), "code": row["settlement__project_code"], "name": row["settlement__project_name"]}
            for row in project_rows
        ],
        "source": {
            "status": source.get_status_display(),
            "reference": source.payment_number,
            "method": source.get_method_display(),
            "timesheetPackRequired": False,
        },
        "summary": {
            "amount": _money(source.amount),
            "allocatedTotal": _money(allocation_summary.get("allocated_total")),
            "allocationCount": int(allocation_summary.get("allocation_count") or 0),
        },
        "existing": _serialize_existing(existing),
    }
