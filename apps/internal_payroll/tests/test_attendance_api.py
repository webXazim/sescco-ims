import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.services import create_branch, create_department, create_employee


class AttendanceApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Attendance API", slug="attendance-api")
        self.user = User.objects.create_user(username="attendance-api-user", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        branch = create_branch(actor_membership=self.membership, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.membership, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.membership,
            employee_number="0001",
            full_name="API Attendance Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )
        self.client.force_login(self.user)

    def test_get_period_is_empty_without_creating_records(self):
        response = self.client.get(reverse("internal_payroll:attendance-api"), {"period": "2026-08"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["period"]["exists"])
        self.assertEqual(payload["records"], {})
        self.assertEqual(len(payload["roster"]), 1)

    def test_patch_persists_attendance_and_returns_revision(self):
        response = self.client.patch(
            reverse("internal_payroll:attendance-api") + "?period=2026-08",
            data=json.dumps({"entries": [{"employee_id": str(self.employee.pk), "date": "2026-08-01", "value": "8"}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["deltaOnly"])
        self.assertNotIn("records", payload)
        self.assertEqual(payload["changes"], [{"employeeId": str(self.employee.pk), "day": 1, "value": "8"}])
        self.assertGreaterEqual(payload["period"]["revision"], 1)
        self.assertTrue(payload["period"]["canEdit"])

    def test_get_period_is_server_paged_and_searchable(self):
        for index in range(2, 32):
            create_employee(
                actor_membership=self.membership,
                employee_number=f"{index:04d}",
                full_name=f"Paged Employee {index:02d}",
                joining_date=date(2020, 1, 1),
                position="Coordinator",
            )
        response = self.client.get(
            reverse("internal_payroll:attendance-api"),
            {"period": "2026-08", "page": 1, "page_size": 25},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["roster"]), 25)
        self.assertEqual(payload["meta"]["count"], 31)
        self.assertEqual(payload["meta"]["totalPages"], 2)

        searched = self.client.get(
            reverse("internal_payroll:attendance-api"),
            {"period": "2026-08", "q": "Paged Employee 31", "page": 1, "page_size": 25},
        ).json()
        self.assertEqual(searched["meta"]["count"], 1)
        self.assertEqual(searched["roster"][0]["name"], "Paged Employee 31")

    def test_rental_role_cannot_read_internal_attendance(self):
        rental_user = User.objects.create_user(username="attendance-rental")
        CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(rental_user)
        response = self.client.get(reverse("internal_payroll:attendance-api"), {"period": "2026-08"})
        self.assertEqual(response.status_code, 403)
