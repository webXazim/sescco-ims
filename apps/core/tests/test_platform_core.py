from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import NotSupportedError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.middleware import CompanyTimezoneMiddleware
from apps.core.models import AuditArea, AuditEvent, Company, CompanySettings
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number, configure_number_sequence

User = get_user_model()


class CompanySettingsTests(TestCase):
    def test_settings_are_created_for_runtime_company(self):
        company = Company.objects.create(name="Acme", slug="acme-core")
        settings = CompanySettings.objects.get(company=company)
        self.assertEqual(settings.timezone, "Asia/Riyadh")
        self.assertEqual(settings.currency_code, "SAR")
        self.assertEqual(settings.country_code, "SA")

    def test_company_setting_codes_are_normalized(self):
        company = Company.objects.create(name="Codes", slug="codes-core")
        settings = company.settings
        settings.currency_code = "aed"
        settings.country_code = "ae"
        settings.save()
        self.assertEqual(settings.currency_code, "AED")
        self.assertEqual(settings.country_code, "AE")

    def test_invalid_timezone_is_rejected(self):
        company = Company.objects.create(name="Timezone", slug="timezone-core")
        settings = company.settings
        settings.timezone = "Not/A-Timezone"
        with self.assertRaises(ValidationError):
            settings.save()


class NumberSequenceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme-numbering")
        self.other_company = Company.objects.create(name="Other", slug="other-numbering")

    def test_numbers_are_monotonic_and_company_scoped(self):
        first = allocate_number(company=self.company, key="inventory.receipt", prefix="RC-", padding=5)
        second = allocate_number(company=self.company, key="inventory.receipt", prefix="RC-", padding=5)
        other = allocate_number(company=self.other_company, key="inventory.receipt", prefix="RC-", padding=5)
        self.assertEqual(first, "RC-00001")
        self.assertEqual(second, "RC-00002")
        self.assertEqual(other, "RC-00001")

    def test_format_is_locked_after_first_issue(self):
        allocate_number(company=self.company, key="payroll.run", prefix="PAY-", padding=6)
        with self.assertRaises(ValidationError):
            allocate_number(company=self.company, key="payroll.run", prefix="NEW-", padding=6)

    def test_format_can_change_before_first_issue(self):
        configure_number_sequence(company=self.company, key="rental.settlement", prefix="SET-", padding=4)
        configure_number_sequence(company=self.company, key="rental.settlement", prefix="ST-", padding=7)
        self.assertEqual(
            allocate_number(company=self.company, key="rental.settlement", prefix="ST-", padding=7),
            "ST-0000001",
        )


class AuditEventTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Audit", slug="audit-core")
        self.user = User.objects.create_user(
            username="audit-user",
            first_name="Platform",
            last_name="Admin",
            email="audit@example.com",
            password="safe-password-for-test",
        )

    def test_audit_supports_existing_ims_user_and_opaque_request_id(self):
        request = RequestFactory().post("/app/", HTTP_USER_AGENT="Test Browser")
        request.request_id = "ims-request-1234"
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        event = record_audit_event(
            company=self.company,
            area=AuditArea.INVENTORY,
            action="inventory.test.changed",
            object_type="inventory.StockItem",
            object_id="123",
            actor=self.user,
            before={"quantity": 1},
            after={"quantity": 2},
            request=request,
        )
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.actor_username, "audit-user")
        self.assertEqual(event.actor_display_name, "Platform Admin")
        self.assertEqual(event.request_id, "ims-request-1234")
        self.assertEqual(event.ip_address, "127.0.0.1")

    def test_audit_events_are_immutable(self):
        event = record_audit_event(
            company=self.company,
            area=AuditArea.CORE,
            action="core.test.created",
            object_type="core.TestRecord",
            object_id="123",
        )
        event.action = "core.test.changed"
        with self.assertRaises(NotSupportedError):
            event.save()
        with self.assertRaises(NotSupportedError):
            AuditEvent.objects.filter(pk=event.pk).update(action="core.test.changed")
        with self.assertRaises(NotSupportedError):
            AuditEvent.objects.filter(pk=event.pk).delete()


class CompanyTimezoneMiddlewareTests(SimpleTestCase):
    def test_company_timezone_is_active_only_during_request(self):
        request = RequestFactory().get("/")
        request.company = SimpleNamespace(pk="company-1", settings=SimpleNamespace(timezone="Asia/Dubai"))
        observed = {}

        def endpoint(_request):
            observed["timezone"] = timezone.get_current_timezone_name()
            return HttpResponse("ok")

        response = CompanyTimezoneMiddleware(endpoint)(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed["timezone"], "Asia/Dubai")
        self.assertEqual(timezone.get_current_timezone_name(), "Asia/Riyadh")
