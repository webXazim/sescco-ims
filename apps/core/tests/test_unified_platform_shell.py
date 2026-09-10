from django.contrib.auth import get_user_model
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.accounts.selectors import ACTIVE_COMPANY_SESSION_KEY
from apps.core.models import Company


User = get_user_model()


class UnifiedPlatformShellTests(TestCase):
    def make_company(self, name: str, slug: str):
        return Company.objects.create(name=name, legal_name=f"{name} LLC", slug=slug)

    def make_user(self, username: str, company, role: str):
        user = User.objects.create_user(username=username, password="strong-test-password")
        membership = CompanyMembership.objects.create(company=company, user=user, role=role)
        return user, membership

    def test_owner_inventory_shell_exposes_shared_company_and_module_switchers(self):
        company = self.make_company("Unified Co", "unified-co")
        user, _ = self.make_user("unified-owner", company, AccessRole.OWNER)
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-platform-switchers')
        self.assertContains(response, "Inventory Management")
        self.assertContains(response, "Payroll Management")
        self.assertContains(response, "/static/platform/css/shell-switchers.css")
        self.assertContains(response, "/static/platform/js/shell-switchers.js")
        self.assertContains(response, "/static/platform/css/inventory-shell.css")
        self.assertContains(response, "/static/platform/js/inventory-shell.js")
        self.assertContains(response, 'class="inventory-shell-v2"')
        self.assertContains(response, 'data-inventory-sidebar-collapse')
        self.assertContains(response, 'data-inventory-sidebar-resize')
        self.assertContains(response, company.name)

    def test_owner_payroll_shell_uses_same_platform_switchers(self):
        company = self.make_company("Payroll Unified", "payroll-unified")
        user, _ = self.make_user("payroll-owner-shell", company, AccessRole.OWNER)
        self.client.force_login(user)

        response = self.client.get(reverse("core:payroll"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-platform-switchers')
        self.assertContains(response, "Inventory Management")
        self.assertContains(response, "Payroll Management")
        self.assertContains(response, "/static/platform/css/shell-switchers.css")
        self.assertContains(response, "/static/platform/js/shell-switchers.js")
        self.assertContains(response, "/static/platform/css/payroll-shell-fixes.css")
        self.assertContains(response, 'data-ui-v2-version="merge-10"')

    def test_inventory_only_membership_only_lists_inventory_module(self):
        company = self.make_company("Inventory Only", "inventory-only")
        user, _ = self.make_user("inventory-only-shell", company, AccessRole.STOREKEEPER)
        self.client.force_login(user)

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        modules = response.context["PLATFORM_CONTEXT"]["modules"]
        self.assertEqual([item["key"] for item in modules], ["inventory"])

    def test_payroll_only_membership_only_lists_payroll_module(self):
        company = self.make_company("Payroll Only", "payroll-only")
        user, _ = self.make_user("payroll-only-shell", company, AccessRole.INTERNAL_PAYROLL_OFFICER)
        self.client.force_login(user)

        response = self.client.get(reverse("core:payroll"))

        self.assertEqual(response.status_code, 200)
        modules = response.context["PLATFORM_CONTEXT"]["modules"]
        self.assertEqual([item["key"] for item in modules], ["payroll"])

    def test_timesheet_focus_mode_removes_v2_shell_offsets(self):
        css = (Path(settings.BASE_DIR) / "static/platform/css/payroll-shell-fixes.css").read_text(encoding="utf-8")
        self.assertIn("body.timesheet-focus-mode .ui-v2-app-shell > .ui-v2-sidebar", css)
        self.assertIn("body.timesheet-focus-mode .ui-v2-topbar", css)
        self.assertIn("margin-left: 0 !important;", css)
        self.assertIn("width: 100vw !important;", css)

    def test_company_switch_preserves_payroll_module_when_destination_allows_it(self):
        first = self.make_company("First Payroll", "first-payroll")
        second = self.make_company("Second Payroll", "second-payroll")
        user, _ = self.make_user("multi-payroll", first, AccessRole.INTERNAL_PAYROLL_OFFICER)
        CompanyMembership.objects.create(company=second, user=user, role=AccessRole.RENTAL_MANPOWER_OFFICER)
        self.client.force_login(user)
        session = self.client.session
        session[ACTIVE_COMPANY_SESSION_KEY] = str(first.id)
        session.save()

        response = self.client.post(
            reverse("accounts:activate-company", args=[second.id]),
            {"module": "payroll"},
        )

        self.assertRedirects(response, reverse("core:payroll"), fetch_redirect_response=False)
        self.assertEqual(self.client.session[ACTIVE_COMPANY_SESSION_KEY], str(second.id))

    def test_company_switch_falls_back_when_destination_lacks_current_module(self):
        payroll_company = self.make_company("Payroll Co", "payroll-co")
        inventory_company = self.make_company("Inventory Co", "inventory-co")
        user, _ = self.make_user("mixed-company-user", payroll_company, AccessRole.INTERNAL_PAYROLL_OFFICER)
        CompanyMembership.objects.create(company=inventory_company, user=user, role=AccessRole.STOREKEEPER)
        self.client.force_login(user)
        session = self.client.session
        session[ACTIVE_COMPANY_SESSION_KEY] = str(payroll_company.id)
        session.save()

        response = self.client.post(
            reverse("accounts:activate-company", args=[inventory_company.id]),
            {"module": "payroll"},
        )

        self.assertRedirects(response, reverse("accounts:home"), fetch_redirect_response=False)
        follow = self.client.get(reverse("accounts:home"))
        self.assertRedirects(follow, reverse("core:dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session[ACTIVE_COMPANY_SESSION_KEY], str(inventory_company.id))
