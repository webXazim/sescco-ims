from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import date
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import branch_scope_ids, membership_allows_project, membership_has_permission
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number
from apps.internal_payroll.models import (
    AttendancePeriod,
    AttendancePeriodStatus,
    PayrollRunLine,
    PayrollRunStatus,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
)
from apps.rental_manpower.services import assert_supplier_settlement_integrity
from apps.rental_manpower.models import (
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    SupplierPayment,
    SupplierPaymentStatus,
    SupplierSettlement,
    RentalSettlementStatus,
)

from ..models import BusinessDocument, DocumentType, DocumentWorkspace, production_document_label
from ..schema import (
    LEGACY_DOCUMENT_SCHEMA_VERSION,
    document_schema_version_for_type,
)
from .supplier_timesheet_pack import build_supplier_timesheet_pack_snapshot
from .amounts import money_to_words


_FINAL_PAYROLL = {
    PayrollRunStatus.APPROVED,
    PayrollRunStatus.PAYMENT_PROCESSING,
    PayrollRunStatus.PAID,
    PayrollRunStatus.CLOSED,
}
SUPPLIER_TIMESHEET_ALIAS = "supplier_timesheet"
PROJECT_TIMESHEET_VARIANT = "project_timesheet"
SUPPLIER_TIMESHEET_VARIANT = "supplier_timesheet"


_FINAL_SETTLEMENT = {
    RentalSettlementStatus.APPROVED,
    RentalSettlementStatus.PAYMENT_PROCESSING,
    RentalSettlementStatus.PARTIALLY_PAID,
    RentalSettlementStatus.PAID,
    RentalSettlementStatus.CLOSED,
}


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _money(value: Decimal | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def _hours(value: Decimal | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def _decimal(value, *, field: str, default=None) -> Decimal:
    if value is None and default is not None:
        value = default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid decimal amount."}) from exc
    if not result.is_finite():
        raise ValidationError({field: "Enter a finite decimal amount."})
    return result


def _period(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _user_name(user) -> str:
    if not user:
        return ""
    return user.get_full_name().strip() or user.username


def _salary_slip_snapshot(line: PayrollRunLine) -> tuple[dict[str, Any], str, str, date, str]:
    run = line.run
    if run.status not in _FINAL_PAYROLL:
        raise ValidationError("Salary slips can be finalized only from Approved or later payroll runs.")
    components = [
        {
            "code": item.component_code,
            "name": item.component_name,
            "category": item.component_category,
            "amount": _money(item.amount),
            "base_amount": _money(item.base_amount),
            "effective_from": item.effective_from.isoformat(),
            "effective_to": item.effective_to.isoformat(),
        }
        for item in line.components.all()
    ]
    adjustments = [
        {
            "type": item.adjustment_type,
            "label": item.adjustment_label,
            "effect": item.effect,
            "amount": _money(item.amount),
            "reference": item.reference,
            "reason": item.reason,
            "date": item.transaction_date.isoformat(),
        }
        for item in line.adjustments.all()
    ]
    payment_row = (
        line.payment_rows.filter(claim_active=True).select_related("batch").order_by("-created_at").first()
        or line.payment_rows.filter(status=SalaryPaymentRowStatus.PAID).select_related("batch").order_by("-paid_at", "-created_at").first()
    )
    payment = {
        "status": payment_row.status if payment_row else "not_paid",
        "status_label": payment_row.get_status_display() if payment_row else "Not paid",
        "paid_by": "Bank" if payment_row and payment_row.status == SalaryPaymentRowStatus.PAID else "",
        "channel": payment_row.batch.channel if payment_row else "",
        "channel_label": payment_row.batch.get_channel_display() if payment_row else "",
        "transaction_reference": payment_row.transaction_reference if payment_row else "",
        "paid_at": payment_row.paid_at.isoformat() if payment_row and payment_row.paid_at else None,
        "bank_name": payment_row.bank_name if payment_row else "",
    }
    snapshot = {
        "kind": DocumentType.SALARY_SLIP,
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "payroll_status": run.status,
        "employee": {
            "number": line.employee_number,
            "name": line.employee_name,
            "branch_code": line.branch_code,
            "branch": line.branch_name,
            "department_code": line.department_code,
            "department": line.department_name,
            "position": line.position,
            "national_id": line.employee.national_id,
            "address": line.employee.address,
            "phone": line.employee.phone,
        },
        "attendance": {
            "regular_hours": _hours(line.regular_hours),
            "overtime_hours": _hours(line.overtime_hours),
            "absent_days": line.absent_days,
            "leave_days": line.leave_days,
            "sick_days": line.sick_days,
            "holiday_days": line.holiday_days,
            "off_days": line.off_days,
        },
        "earnings": {
            "basic": _money(line.basic),
            "allowances": _money(line.allowances),
            "overtime": _money(line.overtime_amount),
            "other_earnings": _money(line.other_earnings),
            "gross": _money(line.gross),
        },
        "deductions": {
            "advance_recovery": _money(line.advance_recovery),
            "other_deductions": _money(line.other_deductions),
            "total": _money(line.total_deductions),
        },
        "net": _money(line.net),
        "payment": payment,
        "components": components,
        "adjustments": adjustments,
        "payroll_snapshot_fingerprint": run.snapshot_fingerprint,
    }
    return snapshot, line.employee_number, line.employee_name, run.period_start, f"Payroll {run.period_start:%Y-%m}"


def _internal_timesheet_snapshot(period: AttendancePeriod) -> tuple[dict[str, Any], str, str, date, str]:
    if period.status != AttendancePeriodStatus.LOCKED:
        raise ValidationError("Internal timesheet documents require a Locked attendance period.")
    entries = list(period.entries.select_related("employee").order_by("employee__employee_number", "work_date"))
    overtime = list(period.overtime_entries.select_related("employee").order_by("employee__employee_number"))
    snapshot = {
        "kind": DocumentType.INTERNAL_TIMESHEET,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "attendance_revision": period.revision,
        "status": period.status,
        "entries": [
            {
                "employee_number": item.employee.employee_number,
                "employee_name": item.employee.full_name,
                "date": item.work_date.isoformat(),
                "hours": _hours(item.regular_hours),
                "code": item.code,
                "note": item.note,
            }
            for item in entries
        ],
        "overtime": [
            {
                "employee_number": item.employee.employee_number,
                "employee_name": item.employee.full_name,
                "hours": _hours(item.hours),
                "amount": _money(item.amount),
                "rate": str(item.overtime_rate),
            }
            for item in overtime
        ],
    }
    return snapshot, period.period_start.strftime("%Y-%m"), "Internal Company", period.period_start, f"Attendance {period.period_start:%Y-%m}"


def _salary_payment_receipt_snapshot(row: SalaryPaymentRow) -> tuple[dict[str, Any], str, str, date, str]:
    if row.status != SalaryPaymentRowStatus.PAID:
        raise ValidationError("Salary payment receipts require a Paid salary-payment row.")
    snapshot = {
        "kind": DocumentType.SALARY_PAYMENT_RECEIPT,
        "period_start": row.batch.run.period_start.isoformat(),
        "employee": {"number": row.employee_number, "name": row.employee_name},
        "payment": {
            "batch_reference": row.batch.reference,
            "channel": row.batch.channel,
            "channel_label": row.batch.get_channel_display(),
            "amount": _money(row.amount),
            "status": row.status,
            "transaction_reference": row.transaction_reference,
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "bank_name": row.bank_name,
            "destination_type": row.destination_type,
        },
    }
    return snapshot, row.employee_number, row.employee_name, row.batch.run.period_start, row.transaction_reference or row.batch.reference


def _rental_timesheet_snapshot(period: RentalTimesheetPeriod) -> tuple[dict[str, Any], str, str, date, str]:
    if period.status != RentalTimesheetStatus.LOCKED:
        raise ValidationError("Rental timesheet documents require a Locked project timesheet.")
    entries = list(period.entries.select_related("worker").order_by("worker__worker_number", "work_date"))
    overtime = list(period.overtime_entries.select_related("worker").order_by("worker__worker_number"))
    snapshot = {
        "kind": DocumentType.RENTAL_TIMESHEET,
        "document_variant": PROJECT_TIMESHEET_VARIANT,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "revision": period.revision,
        "project": {"code": period.project.code, "name": period.project.name},
        "entries": [
            {
                "worker_number": item.worker.worker_number,
                "worker_name": item.worker.full_name,
                "supplier_code": item.supplier_code,
                "supplier_name": item.supplier_name,
                "date": item.work_date.isoformat(),
                "hours": _hours(item.regular_hours),
                "code": item.code,
                "trade": item.trade,
                "rate_type": item.rate_type,
                "rate": str(item.rate),
            }
            for item in entries
        ],
        "overtime": [
            {
                "worker_number": item.worker.worker_number,
                "worker_name": item.worker.full_name,
                "supplier_code": item.supplier_code,
                "supplier_name": item.supplier_name,
                "trade": item.trade,
                "hours": _hours(item.hours),
                "rate": str(item.rate),
            }
            for item in overtime
        ],
    }
    return snapshot, period.project.code, period.project.name, period.period_start, f"Timesheet {period.project.code} {period.period_start:%Y-%m}"


def _supplier_timesheet_snapshot(period: RentalTimesheetPeriod, *, supplier_code: str) -> tuple[dict[str, Any], str, str, date, str]:
    if period.status != RentalTimesheetStatus.LOCKED:
        raise ValidationError("Supplier Timesheet Statements require a Locked project timesheet.")
    supplier_code = str(supplier_code or "").strip().upper()
    if not supplier_code:
        raise ValidationError({"supplier_code": "Supplier is required for a Supplier Timesheet Statement."})
    entries = list(
        period.entries.select_related("worker")
        .filter(supplier_code__iexact=supplier_code)
        .order_by("worker__worker_number", "work_date")
    )
    overtime = list(
        period.overtime_entries.select_related("worker")
        .filter(supplier_code__iexact=supplier_code)
        .order_by("worker__worker_number")
    )
    if not entries and not overtime:
        raise ValidationError("The selected supplier has no rows in this locked project timesheet.")
    supplier_name = next((item.supplier_name for item in entries if item.supplier_name), "") or next((item.supplier_name for item in overtime if item.supplier_name), "") or supplier_code
    worker_ids = {str(item.worker_id) for item in entries} | {str(item.worker_id) for item in overtime}
    regular_hours = sum((item.regular_hours for item in entries), Decimal("0"))
    overtime_hours = sum((item.hours for item in overtime), Decimal("0"))
    snapshot = {
        "kind": DocumentType.RENTAL_TIMESHEET,
        "document_variant": SUPPLIER_TIMESHEET_VARIANT,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "revision": period.revision,
        "project": {"code": period.project.code, "name": period.project.name},
        "supplier": {"code": supplier_code, "name": supplier_name},
        "worker_count": len(worker_ids),
        "regular_hours": _hours(regular_hours),
        "overtime_hours": _hours(overtime_hours),
        "entries": [
            {
                "worker_number": item.worker.worker_number,
                "worker_name": item.worker.full_name,
                "supplier_code": item.supplier_code,
                "supplier_name": item.supplier_name,
                "date": item.work_date.isoformat(),
                "hours": _hours(item.regular_hours),
                "code": item.code,
                "note": item.note,
                "trade": item.trade,
                "rate_type": item.rate_type,
            }
            for item in entries
        ],
        "overtime": [
            {
                "worker_number": item.worker.worker_number,
                "worker_name": item.worker.full_name,
                "supplier_code": item.supplier_code,
                "supplier_name": item.supplier_name,
                "trade": item.trade,
                "hours": _hours(item.hours),
            }
            for item in overtime
        ],
    }
    source_ref = f"Supplier Timesheet {supplier_code} {period.project.code} {period.period_start:%Y-%m}"
    return snapshot, supplier_code, supplier_name, period.period_start, source_ref


def _settlement_snapshot(settlement: SupplierSettlement, *, invoice: dict[str, Any] | None = None) -> tuple[dict[str, Any], str, str, date, str]:
    if settlement.status not in _FINAL_SETTLEMENT:
        raise ValidationError("Settlement documents require an Approved or later supplier settlement.")
    # Document finalization must preserve the already-approved Rental settlement authority;
    # it must never recalculate amounts or depend on a printable Timesheet Pack existing.
    assert_supplier_settlement_integrity(settlement)
    lines = []
    for line in settlement.lines.prefetch_related("rate_lines", "adjustment_lines").all():
        lines.append(
            {
                "worker_number": line.worker_number,
                "worker_name": line.worker_name,
                "trade": line.trade_summary,
                "rate_summary": line.rate_summary,
                "regular_hours": _hours(line.regular_hours),
                "work_days": line.work_days,
                "overtime_hours": _hours(line.overtime_hours),
                "base": _money(line.base_amount),
                "overtime": _money(line.overtime_amount),
                "gross": _money(line.gross_amount),
                "adjustment_earnings": _money(line.adjustment_earnings),
                "adjustment_deductions": _money(line.adjustment_deductions),
                "net": _money(line.net_amount),
            }
        )
    snapshot = {
        "kind": DocumentType.SUPPLIER_INVOICE if invoice is not None else DocumentType.SUPPLIER_SETTLEMENT,
        "period_start": settlement.period_start.isoformat(),
        "period_end": settlement.period_end.isoformat(),
        "settlement_number": settlement.settlement_number,
        "settlement_status": settlement.status,
        "project": {"code": settlement.project_code, "name": settlement.project_name},
        "supplier": {
            "code": settlement.supplier_code,
            "name": settlement.supplier_name,
            "cr_number": settlement.supplier.cr_number,
            "vat_number": settlement.supplier.vat_number,
            "address": settlement.supplier.address,
            "payment_terms": settlement.supplier.payment_terms,
        },
        "totals": {
            "workers": settlement.worker_count,
            "regular_hours": _hours(settlement.total_regular_hours),
            "work_days": settlement.total_work_days,
            "overtime_hours": _hours(settlement.total_overtime_hours),
            "base": _money(settlement.total_base),
            "overtime": _money(settlement.total_overtime),
            "gross": _money(settlement.total_gross),
            "adjustment_earnings": _money(settlement.total_adjustment_earnings),
            "adjustment_deductions": _money(settlement.total_adjustment_deductions),
            "net": _money(settlement.total_net),
        },
        "lines": lines,
        "settlement_snapshot_fingerprint": settlement.snapshot_fingerprint,
        "financial_reconciliation_contract": {
            "version": "1.0",
            "authority": "approved_supplier_settlement",
            "timesheet_pack_required": False,
            "source_timesheet": {
                "id": str(settlement.source_timesheet_id),
                "revision": settlement.source_timesheet_revision,
                "status": settlement.source_timesheet.status,
            },
            "settlement": {
                "id": str(settlement.pk),
                "number": settlement.settlement_number,
                "revision": settlement.revision,
                "status": settlement.status,
                "snapshot_fingerprint": settlement.snapshot_fingerprint,
            },
        },
    }
    if invoice is not None:
        external_number = str(invoice.get("invoice_number") or "").strip().upper()
        issue_date = invoice.get("issue_date")
        subtotal = _decimal(invoice.get("subtotal"), field="subtotal", default=settlement.total_net)
        vat_amount = _decimal(invoice.get("vat_amount"), field="vat_amount", default="0")
        total = _decimal(invoice.get("total"), field="total", default=subtotal + vat_amount)
        if not external_number:
            raise ValidationError({"invoice_number": "Supplier invoice number is required."})
        if not isinstance(issue_date, date):
            raise ValidationError({"issue_date": "Supplier invoice issue date is required."})
        if subtotal < 0 or vat_amount < 0 or total < 0 or total != subtotal + vat_amount:
            raise ValidationError({"total": "Invoice total must equal subtotal plus VAT amount."})
        if subtotal != settlement.total_net:
            raise ValidationError({"subtotal": "Supplier invoice subtotal must equal the approved settlement net amount."})
        vat_rate = (vat_amount * Decimal("100") / subtotal) if subtotal else Decimal("0")
        snapshot["invoice"] = {
            "supplier_invoice_number": external_number,
            "issue_date": issue_date.isoformat(),
            "subtotal": _money(subtotal),
            "vat_amount": _money(vat_amount),
            "vat_rate": f"{vat_rate.quantize(Decimal('0.01')):.2f}",
            "total": _money(total),
            "settlement_net": _money(settlement.total_net),
            "match_basis": "approved_settlement_net",
            "subtotal_variance": _money(subtotal - settlement.total_net),
            "variance": _money(total - (settlement.total_net + vat_amount)),
            "match_status": "matched",
            "payment_terms": settlement.supplier.payment_terms or "",
            "attachment": invoice.get("attachment"),
        }
    return snapshot, settlement.supplier_code, settlement.supplier_name, settlement.period_start, settlement.settlement_number


def _supplier_payment_receipt_snapshot(payment: SupplierPayment) -> tuple[dict[str, Any], str, str, date | None, str]:
    if payment.status != SupplierPaymentStatus.PAID:
        raise ValidationError("Supplier Payment Advice requires a Paid supplier payment.")
    allocations = list(
        payment.allocations.select_related("settlement", "settlement__source_timesheet")
        .order_by("settlement__period_start", "settlement__settlement_number")
    )
    if not allocations:
        raise ValidationError("Supplier Payment Advice requires at least one settlement allocation.")
    allocated_total = sum((Decimal(item.amount or 0) for item in allocations), Decimal("0"))
    if allocated_total != payment.amount:
        raise ValidationError("Supplier Payment Advice allocations must reconcile exactly to the paid amount.")

    period_start = min((item.settlement.period_start for item in allocations), default=None)
    settlement_ids = [item.settlement_id for item in allocations]
    invoice_docs = (
        BusinessDocument.objects.for_company(payment.company)
        .filter(
            document_type=DocumentType.SUPPLIER_INVOICE,
            source_model="rental_manpower.suppliersettlement",
            source_id__in=settlement_ids,
        )
        .order_by("source_id", "-finalized_at")
    )
    invoice_by_settlement: dict[str, BusinessDocument] = {}
    for invoice_doc in invoice_docs:
        if not verify_document_snapshot(invoice_doc):
            raise ValidationError("A Supplier Invoice Received record used by this payment failed its integrity check.")
        invoice_by_settlement.setdefault(str(invoice_doc.source_id), invoice_doc)

    allocation_rows = []
    for item in allocations:
        settlement = item.settlement
        invoice_doc = invoice_by_settlement.get(str(item.settlement_id))
        invoice_snapshot = ((invoice_doc.snapshot or {}).get("invoice") or {}) if invoice_doc else {}
        allocation_rows.append({
            "settlement_id": str(item.settlement_id),
            "settlement_number": settlement.settlement_number,
            "settlement_status": settlement.status,
            "settlement_revision": settlement.revision,
            "period_start": settlement.period_start.isoformat(),
            "project_code": settlement.project_code,
            "project_name": settlement.project_name,
            "source_timesheet_id": str(settlement.source_timesheet_id),
            "source_timesheet_revision": settlement.source_timesheet_revision,
            "settlement_net": _money(settlement.total_net),
            "supplier_invoice_recorded": invoice_doc is not None,
            "supplier_invoice_number": invoice_doc.external_reference if invoice_doc else "",
            "supplier_invoice_total": invoice_snapshot.get("total", "") if invoice_doc else "",
            "amount": _money(item.amount),
        })

    snapshot = {
        "kind": DocumentType.SUPPLIER_PAYMENT_RECEIPT,
        "supplier": {"code": payment.supplier_code, "name": payment.supplier_name},
        "payment": {
            "number": payment.payment_number,
            "date": payment.payment_date.isoformat(),
            "method": payment.method,
            "amount": _money(payment.amount),
            "transaction_reference": payment.transaction_reference,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "note": payment.note,
        },
        "allocations": allocation_rows,
        "financial_reconciliation_contract": {
            "version": "1.0",
            "authority": "paid_supplier_payment",
            "timesheet_pack_required": False,
            "payment": {
                "id": str(payment.pk),
                "number": payment.payment_number,
                "status": payment.status,
            },
            "allocation_count": len(allocation_rows),
            "allocated_total": _money(allocated_total),
        },
    }
    return snapshot, payment.supplier_code, payment.supplier_name, period_start, payment.payment_number


def _load_source(*, company, document_type: str, source_id, invoice: dict[str, Any] | None = None, document_variant: str = "", supplier_code: str = ""):
    if document_type == DocumentType.SALARY_SLIP:
        source = PayrollRunLine.objects.for_company(company).select_related("run", "employee").prefetch_related("components", "adjustments").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _salary_slip_snapshot(source)
    if document_type == DocumentType.INTERNAL_TIMESHEET:
        source = AttendancePeriod.objects.for_company(company).prefetch_related("entries__employee", "overtime_entries__employee").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _internal_timesheet_snapshot(source)
    if document_type == DocumentType.SALARY_PAYMENT_RECEIPT:
        source = SalaryPaymentRow.objects.for_company(company).select_related("batch__run", "employee").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _salary_payment_receipt_snapshot(source)
    if document_type == DocumentType.RENTAL_TIMESHEET:
        source = RentalTimesheetPeriod.objects.for_company(company).select_related("project").prefetch_related("entries__worker", "overtime_entries__worker").get(pk=source_id)
        if document_variant == SUPPLIER_TIMESHEET_VARIANT:
            return DocumentWorkspace.RENTAL, source, _supplier_timesheet_snapshot(source, supplier_code=supplier_code)
        return DocumentWorkspace.RENTAL, source, _rental_timesheet_snapshot(source)
    if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        # The v3 pack aggregator deliberately performs two supplier-filtered reads
        # (daily attendance + monthly OT) instead of prefetching the whole project month.
        source = RentalTimesheetPeriod.objects.for_company(company).select_related("project").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, build_supplier_timesheet_pack_snapshot(source, supplier_code=supplier_code)
    if document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        source = SupplierSettlement.objects.for_company(company).select_related("supplier", "project", "source_timesheet").prefetch_related("lines__rate_lines", "lines__adjustment_lines").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, _settlement_snapshot(source, invoice=invoice if document_type == DocumentType.SUPPLIER_INVOICE else None)
    if document_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
        source = SupplierPayment.objects.for_company(company).select_related("supplier").prefetch_related("allocations__settlement__source_timesheet").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, _supplier_payment_receipt_snapshot(source)
    raise ValidationError({"document_type": "Unsupported document type."})


def _prefix(document_type: str) -> tuple[str, str]:
    return {
        DocumentType.SALARY_SLIP: ("document.salary_slip", "SLIP-"),
        DocumentType.INTERNAL_TIMESHEET: ("document.internal_timesheet", "ITS-"),
        DocumentType.SALARY_PAYMENT_RECEIPT: ("document.salary_receipt", "SRCP-"),
        DocumentType.RENTAL_TIMESHEET: ("document.rental_timesheet", "RTS-"),
        DocumentType.SUPPLIER_TIMESHEET_PACK: ("document.supplier_timesheet_pack", "STP-"),
        DocumentType.SUPPLIER_SETTLEMENT: ("document.supplier_settlement", "SSET-"),
        DocumentType.SUPPLIER_INVOICE: ("document.supplier_invoice", "SINV-"),
        DocumentType.SUPPLIER_PAYMENT_RECEIPT: ("document.supplier_receipt", "PRCP-"),
    }[document_type]


SESCCO_COMPANY_DOCUMENT_HEADPAD = "apps/documents/assets/sescco-company-document-headpad-v2.png"
SESCCO_SUPPLIER_INVOICE_LETTERHEAD = SESCCO_COMPANY_DOCUMENT_HEADPAD


def _packaged_brand_asset_snapshot(relative_path: str) -> dict[str, str]:
    root = Path(settings.BASE_DIR).resolve()
    asset = (root / relative_path).resolve()
    if root not in asset.parents or not asset.is_file():
        raise ValidationError("The packaged SESCCO document-branding asset is unavailable.")
    digest = hashlib.sha256()
    with asset.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "package_path": relative_path,
        "sha256": digest.hexdigest(),
        "content_type": mimetypes.guess_type(asset.name)[0] or "application/octet-stream",
    }


def _brand_asset_snapshot(field) -> dict[str, str] | None:
    if not field or not getattr(field, "name", ""):
        return None
    digest = hashlib.sha256()
    try:
        with field.storage.open(field.name, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (FileNotFoundError, OSError) as exc:
        raise ValidationError("A configured document-branding image is missing from storage.") from exc
    return {
        "storage_key": field.name,
        "sha256": digest.hexdigest(),
        "content_type": mimetypes.guess_type(field.name)[0] or "application/octet-stream",
    }


def _assert_source_scope(*, membership, document_type: str, source) -> None:
    """Fail closed when a finalized document source sits outside the actor scope."""
    if document_type == DocumentType.SALARY_SLIP:
        branch_ids = branch_scope_ids(membership)
        if branch_ids is not None and source.branch_id_snapshot not in set(branch_ids):
            raise PermissionDenied("The salary-slip source is outside your Branch/Office scope.")
        return
    if document_type == DocumentType.INTERNAL_TIMESHEET:
        if membership.branch_scope_mode != "all":
            raise PermissionDenied("Whole-company Internal Timesheet documents require company-wide Branch/Office scope.")
        return
    if document_type == DocumentType.SALARY_PAYMENT_RECEIPT:
        branch_ids = branch_scope_ids(membership)
        if branch_ids is not None and source.run_line.branch_id_snapshot not in set(branch_ids):
            raise PermissionDenied("The salary-payment source is outside your Branch/Office scope.")
        return
    if document_type in {DocumentType.RENTAL_TIMESHEET, DocumentType.SUPPLIER_TIMESHEET_PACK}:
        if not membership_allows_project(membership, source.project):
            raise PermissionDenied("The Rental Timesheet source is outside your Project scope.")
        return
    if document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        if not membership_allows_project(membership, source.project):
            raise PermissionDenied("The supplier-settlement source is outside your Project scope.")
        return
    if document_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
        allocations = list(source.allocations.select_related("settlement__project"))
        if not allocations or any(not membership_allows_project(membership, item.settlement.project) for item in allocations):
            raise PermissionDenied("Supplier payment receipts are available only when every allocation is inside your Project scope.")


@transaction.atomic
def finalize_business_document(
    *,
    actor_membership,
    document_type: str,
    source_id,
    invoice: dict[str, Any] | None = None,
    document_variant: str = "",
    supplier_code: str = "",
    request=None,
    allow_supplier_timesheet_pack: bool = False,
) -> BusinessDocument:
    company = actor_membership.company
    requested_type = str(document_type or "").strip()
    if requested_type == SUPPLIER_TIMESHEET_ALIAS:
        requested_type = DocumentType.RENTAL_TIMESHEET
        document_variant = SUPPLIER_TIMESHEET_VARIANT
    elif requested_type == DocumentType.RENTAL_TIMESHEET and not document_variant:
        document_variant = PROJECT_TIMESHEET_VARIANT
    try:
        normalized_type = DocumentType(requested_type).value
    except ValueError as exc:
        raise ValidationError({"document_type": "Unsupported document type."}) from exc
    if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK and not allow_supplier_timesheet_pack:
        raise ValidationError({
            "document_type": "Supplier Timesheet Pack creation is not yet exposed through the generic Documents API."
        })

    workspace, source, payload = _load_source(company=company, document_type=normalized_type, source_id=source_id, invoice=invoice, document_variant=document_variant, supplier_code=supplier_code)
    required = AccessPermission.INTERNAL_DOCUMENTS_FINALIZE if workspace == DocumentWorkspace.INTERNAL else AccessPermission.RENTAL_DOCUMENTS_FINALIZE
    if not (membership_has_permission(actor_membership, required) or membership_has_permission(actor_membership, AccessPermission.SHARED_DOCUMENTS_FINALIZE)):
        raise PermissionDenied("Your access profile cannot create documents for this workspace.")
    _assert_source_scope(membership=actor_membership, document_type=normalized_type, source=source)

    if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        # Serialize finalization for the same locked project-timesheet source.  The
        # document table already has a unique source/type constraint, but without
        # locking two simultaneous browser retries can both pass the initial
        # existence check and one request then fails at INSERT.  Locking the
        # immutable source row makes v3 pack creation retry-safe without changing
        # its source authority or creating a mutable document state.
        source.__class__._default_manager.select_for_update().only("pk").get(pk=source.pk)

    snapshot, entity_ref, entity_name, period_start, source_reference = payload
    source_model = source._meta.label_lower
    if (
        normalized_type == DocumentType.RENTAL_TIMESHEET and document_variant == SUPPLIER_TIMESHEET_VARIANT
    ) or normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        normalized_supplier_code = str(entity_ref or supplier_code or "").strip().upper()
        source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{normalized_supplier_code}"
    existing = BusinessDocument.objects.for_company(company).filter(
        document_type=normalized_type,
        source_model=source_model,
        source_id=source.pk,
    ).first()
    if existing:
        if verify_document_snapshot(existing):
            return existing
        raise ValidationError("An existing final document failed its integrity check.")

    company_settings = getattr(company, "settings", None)
    snapshot = dict(snapshot)
    logo = _brand_asset_snapshot(getattr(company_settings, "document_logo", None))
    letterhead = _brand_asset_snapshot(getattr(company_settings, "document_letterhead", None))
    watermark = _brand_asset_snapshot(getattr(company_settings, "document_watermark", None))
    branding_mode = getattr(company_settings, "document_branding_mode", "standard")
    branding_profile = "company_settings"
    if normalized_type == DocumentType.SUPPLIER_INVOICE:
        # The Supplier Invoice Received record is an SESCCO internal matching record.
        # It uses the approved company headpad; the supplier's original invoice remains
        # attached separately and is never reproduced as a buyer-issued tax invoice.
        letterhead = _packaged_brand_asset_snapshot(SESCCO_SUPPLIER_INVOICE_LETTERHEAD)
        watermark = None
        branding_mode = "letterhead"
        branding_profile = "sescco_supplier_invoice_received_v1"
    elif not letterhead:
        # This deployment is a single-company SESCCO workspace. When no company-specific
        # letterhead has been uploaded yet, finalized payroll documents still need to use the
        # approved company headpad so every newly generated document prints on the correct form.
        letterhead = _packaged_brand_asset_snapshot(SESCCO_COMPANY_DOCUMENT_HEADPAD)
        watermark = None
        branding_mode = "letterhead"
        branding_profile = "sescco_company_headpad_v1"
    elif branding_mode == "letterhead" and not letterhead:
        branding_mode = "standard"
    snapshot["issuer"] = {
        "name": company.name,
        "legal_name": company.legal_name or company.name,
        "currency": getattr(company_settings, "currency_code", "SAR"),
        "country": getattr(company_settings, "country_code", "SA"),
        "timezone": getattr(company_settings, "timezone", "Asia/Riyadh"),
        "commercial_registration": getattr(company_settings, "commercial_registration", ""),
        "vat_number": getattr(company_settings, "vat_number", ""),
        "address": getattr(company_settings, "document_address", ""),
        "email": getattr(company_settings, "document_email", ""),
        "phone": getattr(company_settings, "document_phone", ""),
        "website": getattr(company_settings, "website", ""),
        "branding": {
            "mode": branding_mode,
            "logo": logo,
            "letterhead": letterhead,
            "watermark": watermark,
            "profile": branding_profile,
        },
    }
    if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        snapshot["document_schema_version"] = document_schema_version_for_type(normalized_type)
    else:
        # Keep this explicit legacy assignment as a compatibility guard for every v2 document family.
        snapshot["document_schema_version"] = LEGACY_DOCUMENT_SCHEMA_VERSION
    currency = snapshot["issuer"]["currency"]
    if normalized_type == DocumentType.SALARY_SLIP:
        snapshot["salary_in_words"] = money_to_words(snapshot["net"], currency)
    elif normalized_type == DocumentType.SALARY_PAYMENT_RECEIPT:
        snapshot["payment"]["amount_in_words"] = money_to_words(snapshot["payment"]["amount"], currency)
    elif normalized_type == DocumentType.SUPPLIER_INVOICE:
        snapshot["invoice"]["total_in_words"] = money_to_words(snapshot["invoice"]["total"], currency)
    elif normalized_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
        snapshot["payment"]["amount_in_words"] = money_to_words(snapshot["payment"]["amount"], currency)
    if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        # Bind the source fingerprint to the supplier-qualified locked operational extract,
        # not to issuer branding or other presentation metadata added during finalization.
        source_fingerprint = _json_hash({
            "source_model": source_model,
            "source": snapshot.get("source"),
            "project": snapshot.get("project"),
            "supplier": snapshot.get("supplier"),
            "summary": snapshot.get("summary"),
            "workers": snapshot.get("workers"),
        })
    else:
        source_fingerprint = getattr(source, "snapshot_fingerprint", "") or getattr(source, "source_fingerprint", "") or _json_hash({
            "model": source_model,
            "id": str(source.pk),
            "updated_at": source.updated_at.isoformat(),
        })
    snapshot_fingerprint = _json_hash(snapshot)
    if normalized_type == DocumentType.RENTAL_TIMESHEET and document_variant == SUPPLIER_TIMESHEET_VARIANT:
        key, prefix = "document.supplier_timesheet", "STS-"
    else:
        key, prefix = _prefix(normalized_type)
    number = allocate_number(company=company, key=key, prefix=prefix, padding=7)
    title = production_document_label(normalized_type)
    if normalized_type == DocumentType.SALARY_SLIP:
        title = f"Salary Slip · {entity_name}"
    elif normalized_type == DocumentType.RENTAL_TIMESHEET:
        if document_variant == SUPPLIER_TIMESHEET_VARIANT:
            title = f"Supplier Timesheet Statement · {entity_name} · {snapshot['project']['name']}"
        else:
            title = f"Project Timesheet · {entity_name}"
    elif normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK:
        title = f"Supplier Monthly Timesheet Pack · {entity_name} · {snapshot['project']['name']}"
    elif normalized_type == DocumentType.SUPPLIER_SETTLEMENT:
        title = f"Supplier Settlement Statement · {entity_name}"
    elif normalized_type == DocumentType.SUPPLIER_INVOICE:
        title = f"Supplier Invoice Received · {entity_name}"
    elif normalized_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
        title = f"Supplier Payment Advice · {entity_name}"

    external_reference = ""
    if normalized_type == DocumentType.SUPPLIER_INVOICE:
        external_reference = snapshot["invoice"]["supplier_invoice_number"]

    document = BusinessDocument.objects.create(
        company=company,
        workspace=workspace,
        document_type=normalized_type,
        document_number=number,
        period_start=period_start,
        title=title,
        entity_reference=entity_ref,
        entity_name=entity_name,
        source_model=source_model,
        source_id=source.pk,
        source_reference=source_reference,
        external_reference=external_reference,
        snapshot=snapshot,
        source_fingerprint=source_fingerprint,
        snapshot_fingerprint=snapshot_fingerprint,
        finalized_at=timezone.now(),
        finalized_by=actor_membership.user,
    )
    record_audit_event(
        company=company,
        area=AuditArea.DOCUMENTS,
        action="documents.finalized",
        object_type="BusinessDocument",
        object_id=document.pk,
        object_label=document.document_number,
        actor_membership=actor_membership,
        after={
            "document_number": document.document_number,
            "document_type": document.document_type,
            "workspace": document.workspace,
            "source_model": document.source_model,
            "source_id": str(document.source_id),
            "document_variant": document_variant or "",
        },
        request=request,
    )
    return document


def verify_document_snapshot(document: BusinessDocument) -> bool:
    return _json_hash(document.snapshot) == document.snapshot_fingerprint
