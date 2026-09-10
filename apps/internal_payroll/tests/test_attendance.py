from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.internal_payroll.models import AttendanceEntry, AttendanceOvertimeEntry, AttendancePeriod, AttendancePeriodStatus
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    create_branch,
    create_department,
    create_employee,
    create_overtime_policy,
    create_salary_component,
    import_attendance_rows,
    save_attendance_entries,
    save_overtime_entries,
    transition_attendance_period,
)


class AttendanceServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Attendance Company", slug="attendance-company")
        self.user = User.objects.create_user(username="attendance-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        branch = create_branch(actor_membership=self.officer, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.officer, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.officer,
            employee_number="0001",
            full_name="Attendance Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )
        self.period_start = date(2026, 8, 1)

    def _complete_month(self):
        rows = []
        day = self.period_start
        while day.month == self.period_start.month:
            rows.append({"employee_id": str(self.employee.pk), "date": day.isoformat(), "value": "8"})
            day += timedelta(days=1)
        save_attendance_entries(actor_membership=self.officer, period_start=self.period_start, entries=rows)

    def test_period_starts_empty_and_first_save_creates_only_explicit_entry(self):
        self.assertFalse(AttendancePeriod.objects.exists())
        save_attendance_entries(
            actor_membership=self.officer,
            period_start=self.period_start,
            entries=[{"employee_id": str(self.employee.pk), "date": "2026-08-01", "value": "8"}],
        )
        period = AttendancePeriod.objects.get(company=self.company, period_start=self.period_start)
        self.assertEqual(period.status, AttendancePeriodStatus.DRAFT)
        self.assertEqual(AttendanceEntry.objects.filter(period=period).count(), 1)

    def test_submission_requires_explicit_value_for_every_employed_day(self):
        save_attendance_entries(
            actor_membership=self.officer,
            period_start=self.period_start,
            entries=[{"employee_id": str(self.employee.pk), "date": "2026-08-01", "value": "8"}],
        )
        with self.assertRaises(ValidationError):
            transition_attendance_period(
                actor_membership=self.officer,
                period_start=self.period_start,
                action="submit",
            )

    def test_submitted_period_is_not_editable(self):
        self._complete_month()
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        with self.assertRaises(ValidationError):
            save_attendance_entries(
                actor_membership=self.officer,
                period_start=self.period_start,
                entries=[{"employee_id": str(self.employee.pk), "date": "2026-08-01", "value": "7"}],
            )

    def test_reviewer_can_approve_and_return_but_cannot_edit(self):
        reviewer_user = User.objects.create_user(username="attendance-reviewer")
        reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        self._complete_month()
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=reviewer, period_start=self.period_start, action="approve")
        period = AttendancePeriod.objects.get(company=self.company, period_start=self.period_start)
        self.assertEqual(period.status, AttendancePeriodStatus.APPROVED)
        with self.assertRaises(PermissionDenied):
            save_attendance_entries(
                actor_membership=reviewer,
                period_start=self.period_start,
                entries=[{"employee_id": str(self.employee.pk), "date": "2026-08-01", "value": "7"}],
            )
        transition_attendance_period(
            actor_membership=reviewer,
            period_start=self.period_start,
            action="return_to_draft",
            reason="Correct attendance evidence.",
        )
        period.refresh_from_db()
        self.assertEqual(period.status, AttendancePeriodStatus.DRAFT)
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="internal.attendance_period.returned_to_draft").exists())

    def test_locked_period_can_return_for_correction_when_no_payroll_snapshot_depends_on_it(self):
        owner_user = User.objects.create_user(username="attendance-owner")
        owner = CompanyMembership.objects.create(company=self.company, user=owner_user, role=AccessRole.OWNER)
        self._complete_month()
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=owner, period_start=self.period_start, action="approve")
        transition_attendance_period(actor_membership=owner, period_start=self.period_start, action="lock")
        period = AttendancePeriod.objects.get(company=self.company, period_start=self.period_start)
        self.assertEqual(period.status, AttendancePeriodStatus.LOCKED)
        transition_attendance_period(
            actor_membership=owner,
            period_start=self.period_start,
            action="return_to_draft",
            reason="Correct source attendance before payroll calculation.",
        )
        period.refresh_from_db()
        self.assertEqual(period.status, AttendancePeriodStatus.DRAFT)

    def test_overtime_uses_effective_salary_snapshot(self):
        basic = create_salary_component(
            actor_membership=self.officer,
            code="BASIC",
            name="Basic Salary",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        policy = create_overtime_policy(
            actor_membership=self.officer,
            code="OT15",
            name="Standard OT",
            base_component_id=basic.pk,
            divisor="240",
            multiplier="1.5",
        )
        structure = assign_employee_salary_structure(
            actor_membership=self.officer,
            employee_id=self.employee.pk,
            effective_from=date(2026, 1, 1),
            overtime_policy_id=policy.pk,
            components=[{"component_id": basic.pk, "amount": "4800"}],
        )
        save_overtime_entries(
            actor_membership=self.officer,
            period_start=self.period_start,
            entries=[{"employee_id": str(self.employee.pk), "hours": "10"}],
        )
        row = AttendanceOvertimeEntry.objects.get(employee=self.employee, period__period_start=self.period_start)
        self.assertEqual(row.salary_structure_id, structure.pk)
        self.assertEqual(row.base_amount, Decimal("4800.00"))
        self.assertEqual(row.multiplier, Decimal("1.5000"))
        self.assertEqual(row.amount, Decimal("300.00"))

    def test_import_dry_run_does_not_create_period_or_entries(self):
        result = import_attendance_rows(
            actor_membership=self.officer,
            period_start=self.period_start,
            rows=[{"employee_number": "0001", "days": {"1": "8", "2": "OFF"}}],
            dry_run=True,
        )
        self.assertTrue(result["valid"])
        self.assertFalse(AttendancePeriod.objects.exists())
        self.assertFalse(AttendanceEntry.objects.exists())
