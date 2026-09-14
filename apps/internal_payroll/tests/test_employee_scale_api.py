from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    create_branch,
    create_department,
    create_employee,
    create_salary_component,
)


class EmployeeScaleApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Employee Scale", slug="employee-scale")
        self.user = User.objects.create_user(username="employee-scale-officer", password="test-password")
        self.officer = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.branch = create_branch(actor_membership=self.officer, code="HQ", name="Head Office")
        self.department = create_department(actor_membership=self.officer, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.officer,
            employee_number="0001",
            full_name="Configured Employee",
            joining_date=date(2020, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Coordinator",
        )
        create_employee(
            actor_membership=self.officer,
            employee_number="0002",
            full_name="Unconfigured Employee",
            joining_date=date(2021, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Assistant",
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
        self.client.force_login(self.user)

    def test_employee_page_does_not_build_full_salary_payment_context(self):
        with patch(
            "apps.internal_payroll.selectors.payment.salary_payment_context",
            side_effect=AssertionError("ordinary employee pagination must not hydrate all payment rows"),
        ) as full_context:
            response = self.client.get(
                reverse("internal_payroll:employees-api"),
                {"period": "2026-08", "page": 1, "page_size": 1, "sort": "employee", "direction": "asc"},
            )
        self.assertEqual(response.status_code, 200)
        full_context.assert_not_called()
        payload = response.json()
        self.assertEqual(payload["meta"]["pageSize"], 1)
        self.assertEqual(payload["meta"]["count"], 2)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["basicSalary"], "4000.00")
        self.assertTrue(payload["results"][0]["salaryConfigured"])

    def test_employee_summary_returns_exact_scope_counts_without_full_master_payload(self):
        response = self.client.get(
            reverse("internal_payroll:employee-summary-api"),
            {"branch": str(self.branch.pk), "period": "2026-08"},
        )
        self.assertEqual(response.status_code, 200)
        summary = response.json()["summary"]
        self.assertEqual(summary["employeeCount"], 2)
        self.assertEqual(summary["activeEmployeeCount"], 2)
        self.assertEqual(summary["salaryConfiguredCount"], 1)
        self.assertEqual(summary["wpsConfiguredCount"], 0)
        self.assertEqual(summary["attendanceEnteredCount"], 0)
        self.assertEqual(summary["departmentDistribution"][0]["count"], 2)
