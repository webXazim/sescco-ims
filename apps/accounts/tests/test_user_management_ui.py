from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.models import CompanyMembership
from apps.accounts.modules import PlatformModule, membership_can_module, module_from_path
from apps.accounts.roles import AccessRole
from apps.core.models import Company


class UserManagementUiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Administration UI Co", slug="administration-ui-co")
        self.owner_user = User.objects.create_user(username="ui-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.access_admin_user = User.objects.create_user(username="ui-access-admin", password="AdminPass!2026")
        self.access_admin = CompanyMembership.objects.create(
            company=self.company, user=self.access_admin_user, role=AccessRole.ACCESS_ADMINISTRATOR
        )
        self.storekeeper_user = User.objects.create_user(username="ui-store", password="StorePass!2026")
        self.storekeeper = CompanyMembership.objects.create(
            company=self.company, user=self.storekeeper_user, role=AccessRole.STOREKEEPER
        )

    def test_administration_module_is_profile_authorized(self):
        self.assertTrue(membership_can_module(self.owner, PlatformModule.ADMINISTRATION))
        self.assertTrue(membership_can_module(self.access_admin, PlatformModule.ADMINISTRATION))
        self.assertFalse(membership_can_module(self.storekeeper, PlatformModule.ADMINISTRATION))
        self.assertTrue(membership_has_permission(self.access_admin, AccessPermission.ACCESS_USERS_MANAGE))

    def test_administration_path_resolves_before_inventory_prefix(self):
        self.assertEqual(module_from_path("/app/administration/"), PlatformModule.ADMINISTRATION)
        self.assertEqual(module_from_path("/app/payroll/"), PlatformModule.PAYROLL)
        self.assertEqual(module_from_path("/app/"), PlatformModule.INVENTORY)

    def test_owner_user_management_page_renders_production_shell_and_api_hooks(self):
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:administration"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Management")
        self.assertContains(response, "Administration")
        self.assertContains(response, 'id="accessUserSearch"')
        self.assertContains(response, 'id="accessUserRows"')
        self.assertContains(response, "Add User")
        self.assertContains(response, "/static/platform/js/access-management.js")
        self.assertContains(response, "/static/platform/css/access-management.css")
        modules = response.context["PLATFORM_CONTEXT"]["modules"]
        self.assertIn("administration", [item["key"] for item in modules])

    def test_access_admin_can_open_administration_without_django_staff(self):
        self.assertFalse(self.access_admin_user.is_staff)
        self.client.force_login(self.access_admin_user)
        response = self.client.get(reverse("accounts:administration"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add User")
        self.assertContains(response, "Django administration is separate")

    def test_storekeeper_cannot_open_administration_and_does_not_see_module(self):
        self.client.force_login(self.storekeeper_user)
        response = self.client.get(reverse("accounts:administration"))
        self.assertEqual(response.status_code, 403)
        inventory = self.client.get(reverse("core:dashboard"))
        modules = inventory.context["PLATFORM_CONTEXT"]["modules"]
        self.assertNotIn("administration", [item["key"] for item in modules])

    def test_module_switcher_marks_administration_current(self):
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:administration"))
        self.assertEqual(response.context["PLATFORM_CONTEXT"]["current_module"], "administration")
        admin_module = next(item for item in response.context["PLATFORM_CONTEXT"]["modules"] if item["key"] == "administration")
        self.assertTrue(admin_module["active"])
        self.assertEqual(admin_module["code"], "AD")
