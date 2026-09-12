from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from io import StringIO

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.rental_manpower.models import (
    RentalAdjustmentStatus,
    RentalSettlementStatus,
    SupplierPaymentStatus,
    SupplierSettlementLine,
)
from apps.rental_manpower.services import (
    assign_worker,
    calculate_project_settlements,
    create_project,
    create_rental_adjustment,
    create_supplier,
    create_worker,
    record_supplier_payment,
    retry_supplier_payment,
    save_timesheet_entries,
    transition_project_settlements,
    transition_rental_adjustment,
    transition_supplier_payment,
    transition_timesheet,
)


class RentalSettlementTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Settlement Co", slug="settlement-co")
        self.user = User.objects.create_user(username="settlement-owner")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.supplier = create_supplier(actor_membership=self.owner, code="SUP-S", name="Supplier S")
        self.project = create_project(
            actor_membership=self.owner,
            code="PRJ-S",
            name="Project S",
            start_date=date(2026, 8, 1),
        )

    def _worker(self, number, name, rate_type, rate, start_day=1):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number=number,
            full_name=name,
        )
        assign_worker(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            trade="Worker",
            rate_type=rate_type,
            rate=rate,
            effective_date=date(2026, 8, start_day),
        )
        return worker

    def _lock_timesheet(self, values_by_worker):
        rows = []
        for worker, start_day, values in values_by_worker:
            for day in range(start_day, 32):
                rows.append({
                    "worker_id": worker.pk,
                    "work_date": date(2026, 8, day),
                    "value": values.get(day, "OFF"),
                })
        save_timesheet_entries(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            entries=rows,
        )
        transition_timesheet(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="submit",
        )
        transition_timesheet(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="approve",
        )
        return transition_timesheet(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="lock",
        )

    def _approve_settlements(self):
        calculate_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
        )
        transition_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="submit",
        )
        return transition_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="approve",
            confirmed=True,
        )

    def test_calculation_requires_locked_timesheet(self):
        worker = self._worker("RW-H", "Hourly Worker", "Hourly", "10")
        save_timesheet_entries(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            entries=[{"worker_id": worker.pk, "work_date": date(2026, 8, 1), "value": "8"}],
        )
        with self.assertRaises(ValidationError):
            calculate_project_settlements(
                actor_membership=self.owner,
                project_id=self.project.pk,
                period_start=date(2026, 8, 1),
            )

    def test_hourly_daily_and_monthly_rate_calculation(self):
        hourly = self._worker("RW-H", "Hourly Worker", "Hourly", "10")
        daily = self._worker("RW-D", "Daily Worker", "Daily", "100")
        monthly = self._worker("RW-M", "Monthly Worker", "Monthly", "3100", start_day=16)
        self._lock_timesheet([
            (hourly, 1, {1: "8", 2: "4"}),
            (daily, 1, {1: "8", 2: "8"}),
            (monthly, 16, {}),
        ])

        settlements = calculate_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
        )
        self.assertEqual(len(settlements), 1)
        lines = {line.worker_id: line for line in SupplierSettlementLine.objects.filter(settlement=settlements[0])}
        self.assertEqual(lines[hourly.pk].base_amount, Decimal("120.00"))
        self.assertEqual(lines[daily.pk].base_amount, Decimal("200.00"))
        self.assertEqual(lines[monthly.pk].base_amount, Decimal("1600.00"))  # 16/31 × SAR 3,100

    def test_approved_adjustments_are_snapshotted(self):
        worker = self._worker("RW-A", "Adjusted Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "8"})])
        bonus = create_rental_adjustment(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            transaction_date=date(2026, 8, 10),
            period_start=date(2026, 8, 1),
            adjustment_type="bonus",
            amount=Decimal("50"),
            reason="Approved bonus",
        )
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=bonus.pk, action="submit")
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=bonus.pk, action="approve")
        fine = create_rental_adjustment(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            transaction_date=date(2026, 8, 11),
            period_start=date(2026, 8, 1),
            adjustment_type="fine",
            amount=Decimal("20"),
            reason="Approved deduction",
        )
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=fine.pk, action="submit")
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=fine.pk, action="approve")

        settlement = calculate_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
        )[0]
        line = SupplierSettlementLine.objects.get(settlement=settlement, worker=worker)
        self.assertEqual(line.gross_amount, Decimal("80.00"))
        self.assertEqual(line.adjustment_earnings, Decimal("50.00"))
        self.assertEqual(line.adjustment_deductions, Decimal("20.00"))
        self.assertEqual(line.net_amount, Decimal("110.00"))

    def test_negative_worker_payable_aborts_calculation(self):
        worker = self._worker("RW-N", "Negative Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "8"})])
        fine = create_rental_adjustment(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            transaction_date=date(2026, 8, 10),
            period_start=date(2026, 8, 1),
            adjustment_type="fine",
            amount=Decimal("100"),
            reason="Excess deduction",
        )
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=fine.pk, action="submit")
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=fine.pk, action="approve")
        with self.assertRaises(ValidationError):
            calculate_project_settlements(
                actor_membership=self.owner,
                project_id=self.project.pk,
                period_start=date(2026, 8, 1),
            )
        self.assertFalse(SupplierSettlementLine.objects.exists())

    def test_adjustment_cannot_be_approved_after_settlement_approval(self):
        worker = self._worker("RW-L", "Locked Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "8"})])
        self._approve_settlements()
        adjustment = create_rental_adjustment(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            transaction_date=date(2026, 8, 12),
            period_start=date(2026, 8, 1),
            adjustment_type="bonus",
            amount=Decimal("10"),
            reason="Late adjustment",
        )
        transition_rental_adjustment(actor_membership=self.owner, adjustment_id=adjustment.pk, action="submit")
        with self.assertRaises(ValidationError):
            transition_rental_adjustment(actor_membership=self.owner, adjustment_id=adjustment.pk, action="approve")
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.status, RentalAdjustmentStatus.REVIEW)

    def test_partial_payment_reserves_balance_failure_frees_it_and_retry_links_history(self):
        worker = self._worker("RW-P", "Paid Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "10"})])
        settlement = self._approve_settlements()[0]
        self.assertEqual(settlement.total_net, Decimal("100.00"))

        first = record_supplier_payment(
            actor_membership=self.owner,
            settlement_id=settlement.pk,
            payment_date=timezone.localdate(),
            method="bank",
            amount=Decimal("60"),
            status="processing",
        )
        with self.assertRaises(ValidationError):
            record_supplier_payment(
                actor_membership=self.owner,
                settlement_id=settlement.pk,
                payment_date=timezone.localdate(),
                method="bank",
                amount=Decimal("50"),
                status="processing",
            )
        transition_supplier_payment(
            actor_membership=self.owner,
            payment_id=first.pk,
            status="failed",
            reason="Bank rejected account",
        )
        retry = retry_supplier_payment(actor_membership=self.owner, payment_id=first.pk, payment_date=timezone.localdate())
        self.assertEqual(retry.retry_of_id, first.pk)
        self.assertEqual(retry.status, SupplierPaymentStatus.PROCESSING)

        # The original payment legitimately has retry_of=NULL.  Tenant reconciliation
        # must ignore an unset nullable FK while still validating the real retry link.
        output = StringIO()
        call_command("merge_rental_manpower_report", "--fail-on-errors", stdout=output)
        self.assertIn("Rental Manpower tenant and shared-project integrity is valid.", output.getvalue())

    def test_reversal_reopens_paid_settlement(self):
        worker = self._worker("RW-R", "Reversed Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "10"})])
        settlement = self._approve_settlements()[0]
        payment = record_supplier_payment(
            actor_membership=self.owner,
            settlement_id=settlement.pk,
            payment_date=timezone.localdate(),
            method="bank",
            amount=Decimal("100"),
            status="paid",
            transaction_reference="BANK-001",
        )
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, RentalSettlementStatus.PAID)
        transition_supplier_payment(
            actor_membership=self.owner,
            payment_id=payment.pk,
            status="reversed",
            reason="Bank reversal",
        )
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, RentalSettlementStatus.APPROVED)


    def test_supplier_payment_dates_follow_approval_chronology(self):
        worker = self._worker("RW-C", "Chronology Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {1: "10"})])
        settlement = self._approve_settlements()[0]

        with self.assertRaises(ValidationError):
            record_supplier_payment(
                actor_membership=self.owner,
                settlement_id=settlement.pk,
                payment_date=timezone.localdate() - timedelta(days=1),
                method="bank",
                amount=Decimal("100"),
                status="processing",
            )

        with self.assertRaises(ValidationError):
            record_supplier_payment(
                actor_membership=self.owner,
                settlement_id=settlement.pk,
                payment_date=timezone.localdate() + timedelta(days=1),
                method="bank",
                amount=Decimal("100"),
                status="paid",
                transaction_reference="BANK-FUTURE",
            )

    def test_zero_net_settlement_can_close_without_zero_value_payment(self):
        worker = self._worker("RW-Z", "Zero Worker", "Hourly", "10")
        self._lock_timesheet([(worker, 1, {})])
        settlement = self._approve_settlements()[0]
        settlement.refresh_from_db()
        self.assertEqual(settlement.total_net, Decimal("0.00"))
        self.assertEqual(settlement.status, RentalSettlementStatus.PAID)
        transition_project_settlements(
            actor_membership=self.owner,
            project_id=self.project.pk,
            period_start=date(2026, 8, 1),
            action="close",
        )
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, RentalSettlementStatus.CLOSED)
