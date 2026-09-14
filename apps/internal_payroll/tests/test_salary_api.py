import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.services import create_branch, create_department, create_employee


class SalarySetupApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="API Company", slug="salary-api")
        self.user = User.objects.create_user(username="salary-api-user", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(self.user)
        branch = create_branch(actor_membership=self.membership, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.membership, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.membership,
            employee_number="0001",
            full_name="API Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )

    def _post_json(self, url, body):
        return self.client.post(url, data=json.dumps(body), content_type="application/json")

    def test_salary_setup_starts_empty_without_seed_records(self):
        response = self.client.get(reverse("internal_payroll:salary-components-api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        response = self.client.get(reverse("internal_payroll:overtime-policies-api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_create_component_policy_and_effective_salary_structure(self):
        basic_response = self._post_json(
            reverse("internal_payroll:salary-components-api"),
            {
                "code": "BASIC",
                "name": "Basic Salary",
                "category": "Earning",
                "recurrence": "Recurring",
                "calculation": "Fixed Amount",
                "wps_mapping": "Basic Salary",
                "status": "Active",
            },
        )
        self.assertEqual(basic_response.status_code, 201)
        basic = basic_response.json()["component"]

        policy_response = self._post_json(
            reverse("internal_payroll:overtime-policies-api"),
            {
                "code": "OT",
                "name": "Standard Overtime",
                "base_component_id": basic["id"],
                "divisor": "240",
                "multiplier": "1.5",
                "status": "Active",
            },
        )
        self.assertEqual(policy_response.status_code, 201)
        policy = policy_response.json()["policy"]

        structure_response = self._post_json(
            reverse("internal_payroll:salary-structures-api"),
            {
                "employee_id": str(self.employee.pk),
                "effective_from": "2025-01-01",
                "overtime_policy_id": policy["id"],
                "components": [{"component_id": basic["id"], "amount": "4000.00"}],
            },
        )
        self.assertEqual(structure_response.status_code, 201)
        payload = structure_response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["structure"]["components"][0]["amount"], "4000.00")
        self.assertEqual(payload["structure"]["otPolicySnapshot"]["multiplier"], "1.5000")
        self.assertEqual(len(payload["history"]), 1)


    def test_salary_structure_directory_is_bounded_and_history_is_employee_scoped(self):
        basic_response = self._post_json(
            reverse("internal_payroll:salary-components-api"),
            {
                "code": "BASIC",
                "name": "Basic Salary",
                "category": "Earning",
                "recurrence": "Recurring",
                "calculation": "Fixed Amount",
                "wps_mapping": "Basic Salary",
                "status": "Active",
            },
        )
        basic = basic_response.json()["component"]
        second = create_employee(
            actor_membership=self.membership,
            employee_number="0002",
            full_name="Second API Employee",
            joining_date=date(2021, 1, 1),
            branch_id=self.employee.organization_assignments.get(effective_to__isnull=True).branch_id,
            department_id=self.employee.organization_assignments.get(effective_to__isnull=True).department_id,
            position="Payroll Analyst",
        )
        self._post_json(
            reverse("internal_payroll:salary-structures-api"),
            {
                "employee_id": str(self.employee.pk),
                "effective_from": "2025-01-01",
                "components": [{"component_id": basic["id"], "amount": "4000.00"}],
            },
        )

        response = self.client.get(
            reverse("internal_payroll:salary-structures-api"),
            {"page": 1, "page_size": 1, "q": "API Employee"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("employee", payload["results"][0])
        self.assertIn("structure", payload["results"][0])
        self.assertEqual(payload["meta"]["pageSize"], 1)
        self.assertEqual(payload["meta"]["coverage"]["employeeCount"], 2)
        self.assertEqual(payload["meta"]["coverage"]["configuredCount"], 1)
        self.assertEqual(payload["meta"]["coverage"]["needsSetupCount"], 1)

        history_response = self.client.get(
            reverse("internal_payroll:salary-structures-api"),
            {"employee": str(self.employee.pk)},
        )
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload["history"]), 1)
        self.assertEqual(history_payload["current"]["employeeId"], str(self.employee.pk))

        needs_setup = self.client.get(
            reverse("internal_payroll:salary-structures-api"),
            {"page": 1, "page_size": 50, "setup": "needs_setup"},
        ).json()
        self.assertEqual([row["employee"]["id"] for row in needs_setup["results"]], [str(second.pk)])

    def test_rental_only_role_cannot_read_salary_setup(self):
        rental_user = User.objects.create_user(username="salary-rental")
        CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(rental_user)
        response = self.client.get(reverse("internal_payroll:salary-components-api"))
        self.assertEqual(response.status_code, 403)
