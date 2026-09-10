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
        self.assertEqual(payload["records"][str(self.employee.pk)]["1"], "8")
        self.assertGreaterEqual(payload["period"]["revision"], 1)

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
