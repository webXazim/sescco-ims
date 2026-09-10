from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, Company
from apps.core.services.audit import record_audit_event


class ManagementAccessBoundaryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Audit Company", slug="audit-company")
        self.other_company = Company.objects.create(name="Other Company", slug="other-audit-company")
        self.user = User.objects.create_user(username="auditor", password="strong-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.READ_ONLY_AUDITOR,
        )
        self.client.force_login(self.user)
        record_audit_event(
            company=self.company,
            area=AuditArea.MANAGEMENT,
            action="test.visible",
            object_type="Test",
            object_id="visible",
            actor_membership=self.membership,
        )
        record_audit_event(
            company=self.other_company,
            area=AuditArea.MANAGEMENT,
            action="test.hidden",
            object_type="Test",
            object_id="hidden",
        )

    def test_management_audit_is_scoped_to_active_company(self):
        response = self.client.get(reverse("platform_api:management-api"), {"period": "2026-08"})
        self.assertEqual(response.status_code, 200)
        actions = {row["action"] for row in response.json()["management"]["audit"]}
        self.assertIn("test.visible", actions)
        self.assertNotIn("test.hidden", actions)

    def test_management_only_auditor_cannot_export_internal_report(self):
        response = self.client.get(
            reverse("platform_api:reports-export-api"),
            {"workspace": "internal", "type": "internal-payroll", "period": "2026-08"},
        )
        self.assertEqual(response.status_code, 403)
