import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.models import PayrollAdjustment, PayrollAdjustmentStatus, PayrollAdjustmentType, PayrollRunStatus
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    create_branch,
    create_department,
    create_employee,
    create_salary_component,
    save_attendance_entries,
    transition_attendance_period,
)


class PayrollApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Payroll API", slug="payroll-api-company")
        self.user = User.objects.create_user(username="payroll-api-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        reviewer_user = User.objects.create_user(username="payroll-api-reviewer", password="test-password")
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
            full_name="Payroll API Employee",
            joining_date=date(2020, 1, 1),
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
            effective_from=date(2025, 1, 1),
            components=[{"component_id": basic.pk, "amount": "4000"}],
        )
        self.period_start = date(2026, 8, 1)
        entries = []
        day = self.period_start
        while day.month == 8:
            entries.append({"employee_id": str(self.employee.pk), "date": day.isoformat(), "value": "8"})
            day += timedelta(days=1)
        save_attendance_entries(actor_membership=self.officer, period_start=self.period_start, entries=entries)
        transition_attendance_period(actor_membership=self.officer, period_start=self.period_start, action="submit")
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="approve")
        self.client.force_login(self.user)

    def test_get_payroll_returns_authoritative_preview_without_creating_run(self):
        response = self.client.get(reverse("internal_payroll:payroll-api"), {"period": "2026-08"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["status"], "Draft")
        self.assertEqual(payload["rows"][0]["net"], "4000.00")
        self.assertFalse(payload["run"]["exists"])

    def test_calculate_endpoint_persists_snapshot(self):
        response = self.client.post(
            reverse("internal_payroll:payroll-calculate-api"),
            data=json.dumps({"period": "2026-08"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["statusValue"], PayrollRunStatus.CALCULATED)
        self.assertEqual(payload["run"]["totals"]["net"], "4000.00")

    def test_adjustment_create_endpoint_always_starts_draft(self):
        response = self.client.post(
            reverse("internal_payroll:payroll-adjustments-api"),
            data=json.dumps(
                {
                    "period": "2026-08",
                    "employee_id": str(self.employee.pk),
                    "transaction_date": "2026-08-15",
                    "adjustment_type": "bonus",
                    "amount": "250",
                    "reason": "Approved business reason",
                    "status": "approved",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        adjustment = PayrollAdjustment.objects.get(pk=response.json()["adjustmentId"])
        self.assertEqual(adjustment.status, PayrollAdjustmentStatus.DRAFT)

    def test_adjustment_register_is_server_paginated_with_exact_period_summary(self):
        for index in range(60):
            PayrollAdjustment.objects.create(
                company=self.company, employee=self.employee, transaction_date=date(2026, 8, (index % 28) + 1),
                period_start=self.period_start, adjustment_type=PayrollAdjustmentType.BONUS, amount="10.00",
                reason=f"Scale adjustment {index}", reference=f"SCALE-{index:03d}",
                status=PayrollAdjustmentStatus.APPROVED if index < 40 else PayrollAdjustmentStatus.DRAFT,
            )
        response = self.client.get(
            reverse("internal_payroll:payroll-adjustments-api"),
            {"period": "2026-08", "page": 1, "page_size": 25, "search": "Scale adjustment", "view": "register"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["surface"], "adjustments_page")
        self.assertEqual(len(payload["results"]), 25)
        self.assertEqual(payload["meta"]["count"], 60)
        self.assertEqual(payload["meta"]["totalPages"], 3)
        self.assertEqual(payload["summary"]["count"], 60)
        self.assertEqual(payload["summary"]["pending"], 20)
        self.assertEqual(float(payload["summary"]["earnings"]), 400.0)

    def test_advance_balance_view_aggregates_in_database_and_pages_people(self):
        PayrollAdjustment.objects.create(
            company=self.company, employee=self.employee, transaction_date=date(2026, 7, 1),
            period_start=date(2026, 7, 1), adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE, amount="1000.00",
            reason="Approved advance", reference="ADV-001", status=PayrollAdjustmentStatus.APPROVED,
        )
        PayrollAdjustment.objects.create(
            company=self.company, employee=self.employee, transaction_date=date(2026, 8, 10),
            period_start=self.period_start, adjustment_type=PayrollAdjustmentType.ADVANCE_RECOVERY, amount="250.00",
            reason="Approved recovery", reference="REC-001", status=PayrollAdjustmentStatus.APPROVED,
        )
        response = self.client.get(
            reverse("internal_payroll:payroll-adjustments-api"),
            {"period": "2026-08", "page": 1, "page_size": 25, "view": "balances"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["balanceSummary"]["activeCount"], 1)
        self.assertEqual(float(payload["balanceSummary"]["outstanding"]), 750.0)
        self.assertEqual(float(payload["balances"][0]["balance"]), 750.0)

    def test_adjustment_mutation_response_is_delta_not_full_payroll_context(self):
        response = self.client.post(
            reverse("internal_payroll:payroll-adjustments-api"),
            data=json.dumps({
                "period": "2026-08", "employee_id": str(self.employee.pk), "transaction_date": "2026-08-20",
                "adjustment_type": "bonus", "amount": "75", "reason": "Delta response test",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIn("adjustment", payload)
        self.assertNotIn("rows", payload)
        self.assertNotIn("adjustmentsByEmployee", payload)
        self.assertEqual(payload["adjustment"]["personName"], self.employee.full_name)

    def test_approval_confirmation_requires_json_boolean_true(self):
        transition_attendance_period(actor_membership=self.reviewer, period_start=self.period_start, action="lock")
        calculate = self.client.post(
            reverse("internal_payroll:payroll-calculate-api"),
            data=json.dumps({"period": "2026-08"}),
            content_type="application/json",
        )
        self.assertEqual(calculate.status_code, 200)
        submit = self.client.post(
            reverse("internal_payroll:payroll-workflow-api"),
            data=json.dumps({"period": "2026-08", "action": "submit_review"}),
            content_type="application/json",
        )
        self.assertEqual(submit.status_code, 200)

        self.client.force_login(self.reviewer.user)
        invalid = self.client.post(
            reverse("internal_payroll:payroll-workflow-api"),
            data=json.dumps({"period": "2026-08", "action": "approve", "confirmed": "true"}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)
        valid = self.client.post(
            reverse("internal_payroll:payroll-workflow-api"),
            data=json.dumps({"period": "2026-08", "action": "approve", "confirmed": True}),
            content_type="application/json",
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["run"]["statusValue"], PayrollRunStatus.APPROVED)

    def test_rental_role_cannot_read_internal_payroll(self):
        rental_user = User.objects.create_user(username="payroll-api-rental")
        CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(rental_user)
        response = self.client.get(reverse("internal_payroll:payroll-api"), {"period": "2026-08"})
        self.assertEqual(response.status_code, 403)
