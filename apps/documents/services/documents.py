from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace
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
from apps.rental_manpower.models import (
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    SupplierPayment,
    SupplierPaymentStatus,
    SupplierSettlement,
    RentalSettlementStatus,
)

from ..models import BusinessDocument, DocumentType, DocumentWorkspace


_FINAL_PAYROLL = {
    PayrollRunStatus.APPROVED,
    PayrollRunStatus.PAYMENT_PROCESSING,
    PayrollRunStatus.PAID,
    PayrollRunStatus.CLOSED,
}
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


_ONES = ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _integer_words(value: int) -> str:
    if value < 0:
        return "Minus " + _integer_words(-value)
    if value < 20:
        return _ONES[value]
    if value < 100:
        return _TENS[value // 10] + ((" " + _ONES[value % 10]) if value % 10 else "")
    if value < 1000:
        return _ONES[value // 100] + " Hundred" + ((" " + _integer_words(value % 100)) if value % 100 else "")
    for divisor, label in ((1_000_000_000, "Billion"), (1_000_000, "Million"), (1000, "Thousand")):
        if value >= divisor:
            return _integer_words(value // divisor) + f" {label}" + ((" " + _integer_words(value % divisor)) if value % divisor else "")
    return str(value)


def _amount_in_words(value: str | Decimal, currency: str) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    whole = int(amount)
    fraction = int((amount - Decimal(whole)) * 100)
    currency = (currency or "SAR").upper()
    major = {"SAR": ("Saudi Riyal", "Saudi Riyals"), "AED": ("UAE Dirham", "UAE Dirhams"), "USD": ("US Dollar", "US Dollars")}.get(currency, (currency, currency))
    minor = {"SAR": ("Halala", "Halalas"), "AED": ("Fils", "Fils"), "USD": ("Cent", "Cents")}.get(currency, ("Cent", "Cents"))
    words = f"{_integer_words(whole)} {major[0] if whole == 1 else major[1]}"
    if fraction:
        words += f" and {_integer_words(fraction)} {minor[0] if fraction == 1 else minor[1]}"
    return words + " Only"


def _salary_payment_snapshot(line: PayrollRunLine) -> dict[str, Any]:
    row = line.payment_rows.filter(claim_active=True).select_related("batch").order_by("-batch__prepared_at").first()
    if row is not None:
        return {
            "paid_by": "Bank",
            "status": row.status,
            "channel": row.batch.channel,
            "transaction_reference": row.transaction_reference,
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "bank_name": row.bank_name,
            "destination_type": row.destination_type,
        }
    try:
        profile = line.employee.payment_profile
    except Exception:
        profile = None
    if profile and profile.is_active:
        return {
            "paid_by": "Bank",
            "status": "pending",
            "channel": "",
            "transaction_reference": "",
            "paid_at": None,
            "bank_name": profile.bank_name,
            "destination_type": profile.destination_type,
        }
    return {"paid_by": "", "status": "not_configured", "channel": "", "transaction_reference": "", "paid_at": None, "bank_name": "", "destination_type": ""}


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
        "payment": _salary_payment_snapshot(line),
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


def _settlement_snapshot(settlement: SupplierSettlement, *, invoice: dict[str, Any] | None = None) -> tuple[dict[str, Any], str, str, date, str]:
    if settlement.status not in _FINAL_SETTLEMENT:
        raise ValidationError("Settlement documents require an Approved or later supplier settlement.")
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
        snapshot["invoice"] = {
            "supplier_invoice_number": external_number,
            "issue_date": issue_date.isoformat(),
            "subtotal": _money(subtotal),
            "vat_amount": _money(vat_amount),
            "total": _money(total),
        }
    return snapshot, settlement.supplier_code, settlement.supplier_name, settlement.period_start, settlement.settlement_number


def _supplier_payment_receipt_snapshot(payment: SupplierPayment) -> tuple[dict[str, Any], str, str, date | None, str]:
    if payment.status != SupplierPaymentStatus.PAID:
        raise ValidationError("Supplier payment receipts require a Paid supplier payment.")
    allocations = list(payment.allocations.select_related("settlement").order_by("settlement__period_start"))
    period_start = min((item.settlement.period_start for item in allocations), default=None)
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
        "allocations": [
            {
                "settlement_number": item.settlement.settlement_number,
                "period_start": item.settlement.period_start.isoformat(),
                "project_code": item.settlement.project_code,
                "project_name": item.settlement.project_name,
                "amount": _money(item.amount),
            }
            for item in allocations
        ],
    }
    return snapshot, payment.supplier_code, payment.supplier_name, period_start, payment.payment_number


def _load_source(*, company, document_type: str, source_id, invoice: dict[str, Any] | None = None):
    if document_type == DocumentType.SALARY_SLIP:
        source = PayrollRunLine.objects.for_company(company).select_related("run", "employee").prefetch_related("components", "adjustments", "payment_rows__batch").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _salary_slip_snapshot(source)
    if document_type == DocumentType.INTERNAL_TIMESHEET:
        source = AttendancePeriod.objects.for_company(company).prefetch_related("entries__employee", "overtime_entries__employee").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _internal_timesheet_snapshot(source)
    if document_type == DocumentType.SALARY_PAYMENT_RECEIPT:
        source = SalaryPaymentRow.objects.for_company(company).select_related("batch__run", "employee").get(pk=source_id)
        return DocumentWorkspace.INTERNAL, source, _salary_payment_receipt_snapshot(source)
    if document_type == DocumentType.RENTAL_TIMESHEET:
        source = RentalTimesheetPeriod.objects.for_company(company).select_related("project").prefetch_related("entries__worker", "overtime_entries__worker").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, _rental_timesheet_snapshot(source)
    if document_type in {DocumentType.SUPPLIER_SETTLEMENT, DocumentType.SUPPLIER_INVOICE}:
        source = SupplierSettlement.objects.for_company(company).select_related("supplier", "project").prefetch_related("lines__rate_lines", "lines__adjustment_lines").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, _settlement_snapshot(source, invoice=invoice if document_type == DocumentType.SUPPLIER_INVOICE else None)
    if document_type == DocumentType.SUPPLIER_PAYMENT_RECEIPT:
        source = SupplierPayment.objects.for_company(company).select_related("supplier").prefetch_related("allocations__settlement").get(pk=source_id)
        return DocumentWorkspace.RENTAL, source, _supplier_payment_receipt_snapshot(source)
    raise ValidationError({"document_type": "Unsupported document type."})


def _prefix(document_type: str) -> tuple[str, str]:
    return {
        DocumentType.SALARY_SLIP: ("document.salary_slip", "SLIP-"),
        DocumentType.INTERNAL_TIMESHEET: ("document.internal_timesheet", "ITS-"),
        DocumentType.SALARY_PAYMENT_RECEIPT: ("document.salary_receipt", "SRCP-"),
        DocumentType.RENTAL_TIMESHEET: ("document.rental_timesheet", "RTS-"),
        DocumentType.SUPPLIER_SETTLEMENT: ("document.supplier_settlement", "SSET-"),
        DocumentType.SUPPLIER_INVOICE: ("document.supplier_invoice", "SINV-"),
        DocumentType.SUPPLIER_PAYMENT_RECEIPT: ("document.supplier_receipt", "PRCP-"),
    }[document_type]


@transaction.atomic
def finalize_business_document(
    *,
    actor_membership,
    document_type: str,
    source_id,
    invoice: dict[str, Any] | None = None,
    request=None,
) -> BusinessDocument:
    company = actor_membership.company
    try:
        normalized_type = DocumentType(document_type).value
    except ValueError as exc:
        raise ValidationError({"document_type": "Unsupported document type."}) from exc

    workspace, source, payload = _load_source(company=company, document_type=normalized_type, source_id=source_id, invoice=invoice)
    if not membership_can_workspace(actor_membership, Workspace(workspace)):
        raise PermissionDenied("Your role cannot create documents for this workspace.")

    snapshot, entity_ref, entity_name, period_start, source_reference = payload
    company_settings = getattr(company, "settings", None)
    snapshot = dict(snapshot)
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
            "logo": getattr(getattr(company_settings, "document_logo", None), "name", "") or "",
            "letterhead": getattr(getattr(company_settings, "document_letterhead", None), "name", "") or "",
            "watermark": getattr(getattr(company_settings, "document_watermark", None), "name", "") or "",
        },
    }
    if normalized_type == DocumentType.SALARY_SLIP:
        snapshot["net_in_words"] = _amount_in_words(snapshot["net"], snapshot["issuer"]["currency"])
    source_model = source._meta.label_lower
    existing = BusinessDocument.objects.for_company(company).filter(
        document_type=normalized_type,
        source_model=source_model,
        source_id=source.pk,
    ).first()
    if existing:
        if verify_document_snapshot(existing):
            return existing
        raise ValidationError("An existing final document failed its integrity check.")

    source_fingerprint = getattr(source, "snapshot_fingerprint", "") or getattr(source, "source_fingerprint", "") or _json_hash({
        "model": source_model,
        "id": str(source.pk),
        "updated_at": source.updated_at.isoformat(),
    })
    snapshot_fingerprint = _json_hash(snapshot)
    key, prefix = _prefix(normalized_type)
    number = allocate_number(company=company, key=key, prefix=prefix, padding=7)
    title = DocumentType(normalized_type).label
    if normalized_type == DocumentType.SALARY_SLIP:
        title = f"Salary Slip · {entity_name}"
    elif normalized_type == DocumentType.RENTAL_TIMESHEET:
        title = f"Rental Timesheet · {entity_name}"
    elif normalized_type == DocumentType.SUPPLIER_SETTLEMENT:
        title = f"Supplier Settlement · {entity_name}"
    elif normalized_type == DocumentType.SUPPLIER_INVOICE:
        title = f"Supplier Invoice · {entity_name}"

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
        },
        request=request,
    )
    return document


def verify_document_snapshot(document: BusinessDocument) -> bool:
    return _json_hash(document.snapshot) == document.snapshot_fingerprint
