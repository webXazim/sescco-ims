from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.internal_payroll.models import (
    AttendanceCode,
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    AttendancePeriodStatus,
    PayrollRun,
    PayrollRunLine,
    PayrollRunStatus,
    SalaryStructure,
)
from apps.internal_payroll.selectors import employee_profile_context
from apps.internal_payroll.services import create_branch, create_department, create_employee


class EmployeeProfileAuthorityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Profile Co", slug="profile-co")
        self.user = User.objects.create_user(username="profile-payroll", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(self.user)
        branch = create_branch(actor_membership=self.membership, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.membership, code="FIN", name="Finance")
        self.employee = create_employee(
            actor_membership=self.membership,
            employee_number="EMP-101",
            full_name="Profile Employee",
            joining_date=date(2024, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Accountant",
        )
        self.period_start = date(2026, 8, 1)
        self.period = AttendancePeriod.objects.create(
            company=self.company,
            period_start=self.period_start,
            period_end=date(2026, 8, 31),
            status=AttendancePeriodStatus.LOCKED,
        )
        AttendanceEntry.objects.create(
            company=self.company,
            period=self.period,
            employee=self.employee,
            work_date=date(2026, 8, 2),
            regular_hours=Decimal("8.00"),
        )
        AttendanceEntry.objects.create(
            company=self.company,
            period=self.period,
            employee=self.employee,
            work_date=date(2026, 8, 3),
            regular_hours=Decimal("0.00"),
            code=AttendanceCode.ABSENT,
        )
        structure = SalaryStructure.objects.create(
            company=self.company,
            employee=self.employee,
            effective_from=date(2026, 1, 1),
            overtime_policy_code="OT-TEST",
            overtime_policy_name="Test overtime",
            overtime_base_component_code="BASIC",
            overtime_base_component_name="Basic Salary",
            overtime_divisor=Decimal("240.0000"),
            overtime_multiplier=Decimal("1.5000"),
        )
        AttendanceOvertimeEntry.objects.create(
            company=self.company,
            period=self.period,
            employee=self.employee,
            salary_structure=structure,
            hours=Decimal("4.00"),
            policy_code="OT-TEST",
            policy_name="Test overtime",
            base_component_code="BASIC",
            base_component_name="Basic Salary",
            base_amount=Decimal("2400.00"),
            divisor=Decimal("240.0000"),
            multiplier=Decimal("1.5000"),
            overtime_rate=Decimal("15.0000"),
            amount=Decimal("60.00"),
        )
        run = PayrollRun.objects.create(
            company=self.company,
            period_start=self.period_start,
            period_end=date(2026, 8, 31),
            attendance_period=self.period,
            attendance_revision=self.period.revision,
            status=PayrollRunStatus.APPROVED,
            revision=1,
            employee_count=1,
            total_basic=Decimal("2400.00"),
            total_allowances=Decimal("300.00"),
            total_overtime=Decimal("60.00"),
            total_other_earnings=Decimal("0.00"),
            total_gross=Decimal("2760.00"),
            total_advance_recovery=Decimal("0.00"),
            total_other_deductions=Decimal("100.00"),
            total_deductions=Decimal("100.00"),
            total_net=Decimal("2660.00"),
        )
        PayrollRunLine.objects.create(
            company=self.company,
            run=run,
            employee=self.employee,
            employee_number=self.employee.employee_number,
            employee_name=self.employee.full_name,
            regular_hours=Decimal("8.00"),
            absent_days=1,
            overtime_hours=Decimal("4.00"),
            overtime_amount=Decimal("60.00"),
            basic=Decimal("2400.00"),
            allowances=Decimal("300.00"),
            gross=Decimal("2760.00"),
            other_deductions=Decimal("100.00"),
            total_deductions=Decimal("100.00"),
            net=Decimal("2660.00"),
        )
        AuditEvent.objects.create(
            company=self.company,
            area=AuditArea.INTERNAL,
            action="internal.payroll_run.approved",
            object_type="internal_payroll.PayrollRun",
            object_id=str(run.pk),
            object_label="August 2026 payroll",
            actor=self.user,
            actor_membership_id=self.membership.pk,
            actor_username=self.user.username,
            actor_display_name="Payroll Officer",
            metadata={"note": "Approved for profile test"},
        )

    def test_selector_returns_real_overtime_payroll_history_and_activity(self):
        profile = employee_profile_context(
            company=self.company,
            employee=self.employee,
            period_start=self.period_start,
        )
        self.assertEqual(profile["attendance"]["present"], 1)
        self.assertEqual(profile["attendance"]["absent"], 1)
        self.assertEqual(Decimal(profile["attendance"]["otHours"]), Decimal("4.00"))
        self.assertEqual(Decimal(profile["attendance"]["otAmount"]), Decimal("60.00"))
        self.assertEqual(len(profile["payrollHistory"]), 1)
        self.assertEqual(Decimal(profile["payrollHistory"][0]["net"]), Decimal("2660.00"))
        self.assertEqual(profile["payrollHistory"][0]["status"], "Approved")
        actions = {row["action"] for row in profile["activity"]}
        self.assertIn("internal.employee.created", actions)
        self.assertIn("internal.payroll_run.approved", actions)

    def test_employee_profile_api_returns_authoritative_profile(self):
        response = self.client.get(
            reverse("internal_payroll:employee-profile-api", kwargs={"employee_id": self.employee.pk}),
            {"period": "2026-08"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"]["employeeNumber"], "EMP-101")
        self.assertEqual(Decimal(payload["profile"]["attendance"]["otHours"]), Decimal("4.00"))
        self.assertEqual(Decimal(payload["profile"]["payrollHistory"][0]["net"]), Decimal("2660.00"))
        self.assertTrue(payload["profile"]["activity"])

    def test_employee_profile_api_rejects_non_month_period(self):
        response = self.client.get(
            reverse("internal_payroll:employee-profile-api", kwargs={"employee_id": self.employee.pk}),
            {"period": "2026-08-15"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
