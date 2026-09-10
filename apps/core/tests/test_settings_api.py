from __future__ import annotations

import json
from datetime import date

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company, CompanySettings
from apps.internal_payroll.models import PayrollRun, PayrollRunStatus


class CompanySettingsApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Settings Company", legal_name="Settings Company LLC", slug="settings-company")
        self.owner = User.objects.create_user(username="settings-owner", password="strong-test-password")
        self.owner_membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner,
            role=AccessRole.OWNER,
        )

    def test_owner_can_read_and_update_company_settings(self):
        self.client.force_login(self.owner)
        response = self.client.patch(
            reverse("platform_api:company-settings-api"),
            data=json.dumps({"companyName": "Settings Operations", "legalName": "Settings Operations LLC", "timezone": "Asia/Dubai", "currency": "AED", "country": "AE"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["settings"]
        self.assertEqual(payload["companyName"], "Settings Operations")
        self.assertEqual(payload["legalName"], "Settings Operations LLC")
        self.assertEqual(payload["timezone"], "Asia/Dubai")
        self.assertEqual(payload["currency"], "AED")
        self.assertEqual(payload["country"], "AE")
        self.assertRegex(payload["today"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(payload["canManage"])

        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Settings Operations")
        self.assertEqual(self.company.legal_name, "Settings Operations LLC")
        settings = CompanySettings.objects.get(company=self.company)
        self.assertEqual(settings.currency_code, "AED")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="company.settings.updated").exists())


    def test_currency_is_locked_after_a_financial_calculation_exists(self):
        PayrollRun.objects.create(
            company=self.company,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            status=PayrollRunStatus.CALCULATED,
            calculated_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        response = self.client.patch(
            reverse("platform_api:company-settings-api"),
            data=json.dumps({"currency": "AED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CompanySettings.objects.get(company=self.company).currency_code, "SAR")

    def test_non_settings_role_is_read_only(self):
        officer = User.objects.create_user(username="settings-officer", password="strong-test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=officer,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(officer)

        read_response = self.client.get(reverse("platform_api:company-settings-api"))
        self.assertEqual(read_response.status_code, 200)
        self.assertFalse(read_response.json()["settings"]["canManage"])

        write_response = self.client.patch(
            reverse("platform_api:company-settings-api"),
            data=json.dumps({"currency": "USD"}),
            content_type="application/json",
        )
        self.assertEqual(write_response.status_code, 403)
        self.assertEqual(CompanySettings.objects.get(company=self.company).currency_code, "SAR")

    def test_invalid_non_text_setting_returns_400(self):
        self.client.force_login(self.owner)
        response = self.client.patch(
            reverse("platform_api:company-settings-api"),
            data=json.dumps({"companyName": None}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("companyName", response.json()["errors"])

    def test_unauthenticated_settings_api_returns_json_401(self):
        response = self.client.get(reverse("platform_api:company-settings-api"))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])
