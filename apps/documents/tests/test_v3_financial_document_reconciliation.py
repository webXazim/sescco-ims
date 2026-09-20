from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.documents.models import DocumentType
from apps.documents.schema import validate_document_snapshot_for_type
from apps.documents.services.documents import _settlement_snapshot, _supplier_payment_receipt_snapshot
from apps.rental_manpower.models import RentalTimesheetStatus, SupplierPaymentStatus


class _FakeLines:
    def __init__(self, rows):
        self.rows = rows

    def prefetch_related(self, *_args):
        return self

    def all(self):
        return list(self.rows)


class _FakeAllocations:
    def __init__(self, rows):
        self.rows = rows

    def select_related(self, *_args):
        return self

    def order_by(self, *_args):
        return list(self.rows)


def _settlement():
    line = SimpleNamespace(
        worker_number="RW-001",
        worker_name="Worker One",
        trade_summary="Mason",
        rate_summary="Hourly SAR 10.00",
        regular_hours=Decimal("10.00"),
        work_days=2,
        overtime_hours=Decimal("1.00"),
        base_amount=Decimal("100.00"),
        overtime_amount=Decimal("0.00"),
        gross_amount=Decimal("100.00"),
        adjustment_earnings=Decimal("5.00"),
        adjustment_deductions=Decimal("3.00"),
        net_amount=Decimal("102.00"),
    )
    return SimpleNamespace(
        pk=uuid.uuid4(),
        status="approved",
        revision=7,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        settlement_number="SET-000101",
        project_code="PRJ-001",
        project_name="Project One",
        supplier_code="SUP-001",
        supplier_name="Supplier One",
        supplier=SimpleNamespace(cr_number="CR-1", vat_number="VAT-1", address="Dammam", payment_terms="30 days"),
        source_timesheet_id=uuid.uuid4(),
        source_timesheet_revision=4,
        source_timesheet=SimpleNamespace(status=RentalTimesheetStatus.LOCKED),
        worker_count=1,
        total_regular_hours=Decimal("10.00"),
        total_work_days=2,
        total_overtime_hours=Decimal("1.00"),
        total_base=Decimal("100.00"),
        total_overtime=Decimal("0.00"),
        total_gross=Decimal("100.00"),
        total_adjustment_earnings=Decimal("5.00"),
        total_adjustment_deductions=Decimal("3.00"),
        total_net=Decimal("102.00"),
        snapshot_fingerprint="a" * 64,
        lines=_FakeLines([line]),
    )


class FinancialDocumentReconciliationContractTests(SimpleTestCase):
    def test_settlement_statement_preserves_approved_totals_and_locked_timesheet_revision(self):
        settlement = _settlement()
        with patch("apps.documents.services.documents.assert_supplier_settlement_integrity") as integrity:
            snapshot, supplier_code, supplier_name, period_start, source_reference = _settlement_snapshot(settlement)
        integrity.assert_called_once_with(settlement)
        self.assertEqual((supplier_code, supplier_name), ("SUP-001", "Supplier One"))
        self.assertEqual(period_start, date(2026, 6, 1))
        self.assertEqual(source_reference, "SET-000101")
        self.assertEqual(snapshot["totals"]["gross"], "100.00")
        self.assertEqual(snapshot["totals"]["adjustment_earnings"], "5.00")
        self.assertEqual(snapshot["totals"]["adjustment_deductions"], "3.00")
        self.assertEqual(snapshot["totals"]["net"], "102.00")
        contract = snapshot["financial_reconciliation_contract"]
        self.assertEqual(contract["authority"], "approved_supplier_settlement")
        self.assertFalse(contract["timesheet_pack_required"])
        self.assertEqual(contract["source_timesheet"]["revision"], 4)
        self.assertEqual(contract["source_timesheet"]["status"], RentalTimesheetStatus.LOCKED)
        self.assertEqual(contract["settlement"]["revision"], 7)
        validate_document_snapshot_for_type(DocumentType.SUPPLIER_SETTLEMENT, snapshot)

    def test_supplier_invoice_received_matches_approved_settlement_net_without_recalculating_it(self):
        settlement = _settlement()
        invoice = {
            "invoice_number": "SUP-INV-88",
            "issue_date": date(2026, 7, 2),
            "subtotal": "102.00",
            "vat_amount": "15.30",
            "total": "117.30",
            "attachment": {"storage_key": "supplier-invoices/invoice.pdf", "original_name": "invoice.pdf"},
        }
        with patch("apps.documents.services.documents.assert_supplier_settlement_integrity"):
            snapshot, *_ = _settlement_snapshot(settlement, invoice=invoice)
        self.assertEqual(snapshot["kind"], DocumentType.SUPPLIER_INVOICE)
        self.assertEqual(snapshot["invoice"]["match_basis"], "approved_settlement_net")
        self.assertEqual(snapshot["invoice"]["settlement_net"], "102.00")
        self.assertEqual(snapshot["invoice"]["subtotal"], "102.00")
        self.assertEqual(snapshot["invoice"]["subtotal_variance"], "0.00")
        self.assertEqual(snapshot["invoice"]["total"], "117.30")
        self.assertEqual(snapshot["invoice"]["match_status"], "matched")
        validate_document_snapshot_for_type(DocumentType.SUPPLIER_INVOICE, snapshot)

    def test_financial_schema_rejects_invoice_or_settlement_math_drift(self):
        settlement = _settlement()
        invoice = {
            "invoice_number": "SUP-INV-89",
            "issue_date": date(2026, 7, 2),
            "subtotal": "102.00",
            "vat_amount": "15.30",
            "total": "117.30",
        }
        with patch("apps.documents.services.documents.assert_supplier_settlement_integrity"):
            snapshot, *_ = _settlement_snapshot(settlement, invoice=invoice)
        broken = deepcopy(snapshot)
        broken["invoice"]["subtotal_variance"] = "1.00"
        with self.assertRaises(ValidationError):
            validate_document_snapshot_for_type(DocumentType.SUPPLIER_INVOICE, broken)
        broken = deepcopy(snapshot)
        broken["totals"]["net"] = "999.00"
        with self.assertRaises(ValidationError):
            validate_document_snapshot_for_type(DocumentType.SUPPLIER_INVOICE, broken)

    def test_payment_advice_allocations_reconcile_exactly_to_paid_payment(self):
        settlement = _settlement()
        allocation = SimpleNamespace(settlement=settlement, settlement_id=settlement.pk, amount=Decimal("102.00"))
        payment = SimpleNamespace(
            pk=uuid.uuid4(),
            company=SimpleNamespace(pk=uuid.uuid4()),
            status=SupplierPaymentStatus.PAID,
            supplier_code="SUP-001",
            supplier_name="Supplier One",
            payment_number="SPAY-000321",
            payment_date=date(2026, 7, 20),
            method="bank",
            amount=Decimal("102.00"),
            transaction_reference="BANK-7788",
            paid_at=None,
            note="June settlement",
            allocations=_FakeAllocations([allocation]),
        )
        with patch("apps.documents.services.documents.BusinessDocument.objects.for_company") as docs:
            docs.return_value.filter.return_value.order_by.return_value = []
            snapshot, *_ = _supplier_payment_receipt_snapshot(payment)
        self.assertEqual(snapshot["financial_reconciliation_contract"]["allocated_total"], "102.00")
        self.assertEqual(snapshot["financial_reconciliation_contract"]["allocation_count"], 1)
        self.assertFalse(snapshot["financial_reconciliation_contract"]["timesheet_pack_required"])
        self.assertEqual(snapshot["allocations"][0]["source_timesheet_revision"], 4)
        self.assertEqual(snapshot["allocations"][0]["settlement_net"], "102.00")
        self.assertFalse(snapshot["allocations"][0]["supplier_invoice_recorded"])
        validate_document_snapshot_for_type(DocumentType.SUPPLIER_PAYMENT_RECEIPT, snapshot)

    def test_payment_advice_rejects_allocation_total_that_differs_from_paid_amount(self):
        settlement = _settlement()
        allocation = SimpleNamespace(settlement=settlement, settlement_id=settlement.pk, amount=Decimal("80.00"))
        payment = SimpleNamespace(
            pk=uuid.uuid4(), company=SimpleNamespace(pk=uuid.uuid4()), status=SupplierPaymentStatus.PAID,
            supplier_code="SUP-001", supplier_name="Supplier One", payment_number="SPAY-000322",
            payment_date=date(2026, 7, 20), method="bank", amount=Decimal("102.00"),
            transaction_reference="BANK-7789", paid_at=None, note="", allocations=_FakeAllocations([allocation]),
        )
        with self.assertRaises(ValidationError):
            _supplier_payment_receipt_snapshot(payment)

    def test_financial_print_language_keeps_invoice_direction_and_source_revisions_unambiguous(self):
        template = (Path(__file__).resolve().parents[3] / "templates/documents/print.html").read_text(encoding="utf-8")
        self.assertIn("Received from supplier", template)
        self.assertIn("Matched to approved settlement net", template)
        self.assertIn("Locked Timesheet Revision", template)
        self.assertIn("Not required for settlement authority", template)
        self.assertIn("Paid allocation reconciliation", template)
        self.assertIn("source_timesheet_revision", template)
