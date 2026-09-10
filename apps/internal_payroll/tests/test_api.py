import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.services import create_branch, create_department


class InternalOrganizationApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme-api")
        self.user = User.objects.create_user(username="payroll", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(self.user)
        self.branch = create_branch(actor_membership=self.membership, code="HQ", name="Head Office")
        self.department = create_department(actor_membership=self.membership, code="OPS", name="Operations")

    def test_create_employee_endpoint_persists_master(self):
        response = self.client.post(
            reverse("internal_payroll:employees-api"),
            data=json.dumps(
                {
                    "employee_number": "0001",
                    "full_name": "API Employee",
                    "joining_date": date(2020, 1, 1).isoformat(),
                    "branch_id": str(self.branch.pk),
                    "department_id": str(self.department.pk),
                    "position": "Supervisor",
                    "status": "Active",
                    "national_id": "",
                    "phone": "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["employee"]["name"], "API Employee")
        self.assertEqual(payload["employee"]["branchId"], str(self.branch.pk))
        self.assertEqual(len(payload["history"]), 1)

    def test_list_branches_is_company_scoped(self):
        other_company = Company.objects.create(name="Other", slug="other-api")
        other_user = User.objects.create_user(username="other")
        other_membership = CompanyMembership.objects.create(company=other_company, user=other_user, role=AccessRole.OWNER)
        create_branch(actor_membership=other_membership, code="OTHER", name="Other Branch")

        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 200)
        codes = {row["code"] for row in response.json()["results"]}
        self.assertEqual(codes, {"HQ"})

    def test_unauthenticated_api_request_returns_json_401(self):
        self.client.logout()
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["ok"], False)

    def test_operations_admin_does_not_gain_payroll_access_from_merge(self):
        operations_user = User.objects.create_user(username="operations-only", password="test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=operations_user,
            role=AccessRole.OPERATIONS_ADMIN,
        )
        self.client.force_login(operations_user)
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)

    def test_role_without_internal_workspace_returns_json_403(self):
        rental_user = User.objects.create_user(username="rental-only", password="test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(rental_user)
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)
