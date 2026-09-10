from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.internal_payroll.models import PayrollRun, PayrollRunLine, PayrollRunStatus
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    calculate_payroll_run,
    create_branch,
    create_department,
    create_employee,
    create_payroll_adjustment,
    create_salary_component,
    save_attendance_entries,
    transition_attendance_period,
    transition_payroll_adjustment,
    transition_payroll_run,
    update_payroll_policy,
)


class PayrollServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Payroll Company", slug="payroll-company")
        self.officer_user = User.objects.create_user(username="payroll-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=self.officer_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.reviewer_user = User.objects.create_user(username="payroll-reviewer", password="test-password")
        self.reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=self.reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        branch = create_branch(actor_membership=self.officer, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.officer, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.officer,
            employee_number="0001",
            full_name="Payroll Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )
        self.branch = branch
        self.department = department
        self.basic = create_salary_component(
            actor_membership=self.officer,
            code="BASIC",
            name="Basic Salary",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        self.housing = create_salary_component(
            actor_membership=self.officer,
            code="HOUSE",
            name="Housing Allowance",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Housing Allowance",
        )
        assign_employee_salary_structure(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            effective_from=date(2025, 1, 1),
            components=[
                {"component_id": self.basic.pk, "amount": "4000"},
                {"component_id": self.housing.pk, "amount": "1000"},
            ],
        )
        self.period_start = date(2026, 8, 1)

    def _complete_attendance(self, employees=None):
        employees = employees or [self.employee]
        rows = []
        for employee in employees:
            day = max(self.period_start, employee.joining_date)
            period_end = date(2026, 8, 31)
            if employee.employment_end_date:
                period_end = min(period_end, employee.employment_end_date)
            while day <= period_end:
                rows.append({"employee_id": str(employee.pk), "date": day.isoformat(), "value": "8"})
                day += timedelta(days=1)
        save_attendance_entries(actor_membership=self.officer, period_start=self.period_start, entries=rows)

    def _approve_attendance(self, *, lock=False):
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="approve")
        if lock:
            transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="lock")

    def _approved_adjustment(self, *, adjustment_type, amount, reason):
        adjustment = create_payroll_adjustment(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            transaction_date=date(2026, 8, 15),
            period_start=self.period_start,
            adjustment_type=adjustment_type,
            amount=Decimal(amount),
            reason=reason,
        )
        transition_payroll_adjustment(actor_membership=self.officer, adjustment_id=adjustment.pk, action="submit")
        transition_payroll_adjustment(actor_membership=self.reviewer, adjustment_id=adjustment.pk, action="approve")
        adjustment.refresh_from_db()
        return adjustment

    def test_full_month_calculates_without_proration_policy(self):
        self._complete_attendance()
        self._approve_attendance()

        run = calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)

        self.assertEqual(run.status, PayrollRunStatus.CALCULATED)
        self.assertEqual(run.employee_count, 1)
        self.assertEqual(run.total_basic, Decimal("4000.00"))
        self.assertEqual(run.total_allowances, Decimal("1000.00"))
        self.assertEqual(run.total_gross, Decimal("5000.00"))
        self.assertEqual(run.total_net, Decimal("5000.00"))
        self.assertTrue(run.source_fingerprint)
        self.assertTrue(run.snapshot_fingerprint)
        self.assertEqual(PayrollRunLine.objects.filter(run=run).count(), 1)

    def test_finance_review_requires_locked_attendance_but_lock_does_not_stale_source(self):
        self._complete_attendance()
        self._approve_attendance()
        run = calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        source_fingerprint = run.source_fingerprint

        with self.assertRaises(ValidationError):
            transition_payroll_run(
                actor_membership=self.officer,
                period_start=self.period_start,
                action="submit_review",
            )

        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="lock")
        transition_payroll_run(
            actor_membership=self.officer,
            period_start=self.period_start,
            action="submit_review",
        )
        run.refresh_from_db()
        self.assertEqual(run.status, PayrollRunStatus.REVIEW)
        self.assertEqual(run.source_fingerprint, source_fingerprint)

    def test_salary_advance_is_balance_only_and_approved_recovery_deducts_payroll(self):
        self._complete_attendance()
        self._approve_attendance(lock=True)
        self._approved_adjustment(adjustment_type="salary_advance", amount="1000", reason="Approved employee advance")
        self._approved_adjustment(adjustment_type="bonus", amount="200", reason="Approved performance bonus")
        self._approved_adjustment(adjustment_type="advance_recovery", amount="250", reason="Monthly advance recovery")

        run = calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)

        self.assertEqual(run.total_other_earnings, Decimal("200.00"))
        self.assertEqual(run.total_gross, Decimal("5200.00"))
        self.assertEqual(run.total_advance_recovery, Decimal("250.00"))
        self.assertEqual(run.total_net, Decimal("4950.00"))
        line = PayrollRunLine.objects.get(run=run, employee=self.employee)
        self.assertEqual(line.adjustments.count(), 2)  # advance issuance is not a payroll earning/deduction

    def test_advance_recovery_cannot_exceed_approved_outstanding_balance(self):
        self._approved_adjustment(adjustment_type="salary_advance", amount="500", reason="Advance issued")
        recovery = create_payroll_adjustment(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            transaction_date=date(2026, 8, 20),
            period_start=self.period_start,
            adjustment_type="advance_recovery",
            amount=Decimal("600"),
            reason="Invalid recovery amount",
        )
        transition_payroll_adjustment(actor_membership=self.officer, adjustment_id=recovery.pk, action="submit")

        with self.assertRaises(ValidationError):
            transition_payroll_adjustment(actor_membership=self.reviewer, adjustment_id=recovery.pk, action="approve")

    def test_future_advance_cannot_fund_an_earlier_recovery(self):
        advance = create_payroll_adjustment(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            transaction_date=date(2026, 8, 25),
            period_start=self.period_start,
            adjustment_type="salary_advance",
            amount=Decimal("1000"),
            reason="Advance issued later in the month",
        )
        transition_payroll_adjustment(actor_membership=self.officer, adjustment_id=advance.pk, action="submit")
        transition_payroll_adjustment(actor_membership=self.reviewer, adjustment_id=advance.pk, action="approve")
        recovery = create_payroll_adjustment(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            transaction_date=date(2026, 8, 20),
            period_start=self.period_start,
            adjustment_type="advance_recovery",
            amount=Decimal("100"),
            reason="Recovery predates the advance",
        )
        transition_payroll_adjustment(actor_membership=self.officer, adjustment_id=recovery.pk, action="submit")

        with self.assertRaises(ValidationError):
            transition_payroll_adjustment(actor_membership=self.reviewer, adjustment_id=recovery.pk, action="approve")

    def test_new_approved_adjustment_after_calculation_forces_recalculation(self):
        self._complete_attendance()
        self._approve_attendance(lock=True)
        calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        self._approved_adjustment(adjustment_type="bonus", amount="100", reason="Approved after initial calculation")

        with self.assertRaises(ValidationError):
            transition_payroll_run(
                actor_membership=self.officer,
                period_start=self.period_start,
                action="submit_review",
            )

    def test_snapshot_tamper_is_detected_before_review(self):
        self._complete_attendance()
        self._approve_attendance(lock=True)
        run = calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        PayrollRunLine.objects.filter(run=run, employee=self.employee).update(net=Decimal("4999.00"))

        with self.assertRaises(ValidationError):
            transition_payroll_run(
                actor_membership=self.officer,
                period_start=self.period_start,
                action="submit_review",
            )

    def test_approved_payroll_cannot_be_recalculated_or_reset(self):
        self._complete_attendance()
        self._approve_attendance(lock=True)
        calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        transition_payroll_run(actor_membership=self.officer, period_start=self.period_start, action="submit_review")
        transition_payroll_run(
            actor_membership=self.reviewer,
            period_start=self.period_start,
            action="approve",
            confirmed=True,
        )

        with self.assertRaises(ValidationError):
            calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        with self.assertRaises(ValidationError):
            transition_payroll_run(
                actor_membership=self.reviewer,
                period_start=self.period_start,
                action="return_for_changes",
                note="Not allowed after approval",
            )
        self.assertTrue(
            AuditEvent.objects.filter(company=self.company, action="internal.payroll_run.approved").exists()
        )

    def test_calculation_is_all_or_nothing_when_any_employee_is_blocked(self):
        second = create_employee(
            actor_membership=self.officer,
            employee_number="0002",
            full_name="Employee Without Salary",
            joining_date=date(2020, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Assistant",
        )
        self._complete_attendance([self.employee, second])
        self._approve_attendance()

        with self.assertRaises(ValidationError):
            calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)

        self.assertFalse(PayrollRun.objects.filter(company=self.company, period_start=self.period_start).exists())
        self.assertFalse(PayrollRunLine.objects.filter(company=self.company).exists())


class PayrollProrationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Proration Company", slug="proration-company")
        user = User.objects.create_user(username="proration-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        reviewer_user = User.objects.create_user(username="proration-reviewer")
        self.reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        branch = create_branch(actor_membership=self.officer, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.officer, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.officer,
            employee_number="0001",
            full_name="Mid-month Joiner",
            joining_date=date(2026, 8, 16),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )
        basic = create_salary_component(
            actor_membership=self.officer,
            code="BASIC",
            name="Basic Salary",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        assign_employee_salary_structure(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            effective_from=date(2026, 8, 16),
            components=[{"component_id": basic.pk, "amount": "4000"}],
        )
        self.period_start = date(2026, 8, 1)
        entries = []
        current = self.employee.joining_date
        while current <= date(2026, 8, 31):
            entries.append({"employee_id": str(self.employee.pk), "date": current.isoformat(), "value": "8"})
            current += timedelta(days=1)
        save_attendance_entries(actor_membership=self.officer, period_start=self.period_start, entries=entries)
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="approve")

    def test_partial_month_requires_explicit_proration_policy(self):
        with self.assertRaises(ValidationError):
            calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)

        update_payroll_policy(actor_membership=self.officer, proration_method="calendar_days")
        run = calculate_payroll_run(actor_membership=self.officer, period_start=self.period_start)
        self.assertEqual(run.total_basic, Decimal("2064.52"))  # 4,000 × 16 / 31
        component = PayrollRunLine.objects.get(run=run).components.get(component_code="BASIC")
        self.assertEqual(component.proration_days, 16)
        self.assertEqual(component.proration_denominator, 31)
