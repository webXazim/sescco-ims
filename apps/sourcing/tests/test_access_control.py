from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission, permissions_for_legacy_role
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.modules import PlatformModule, membership_can_module
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.access import (
    membership_can_manage_manpower_sourcing,
    membership_can_manage_vendor_sourcing,
    membership_can_view_manpower_sourcing,
    membership_can_view_vendor_sourcing,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class SourcingAccessControlTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Sourcing Access Co", slug="sourcing-access-co")
        self.owner_user = User.objects.create_user(username="sourcing-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner_user,
            role=AccessRole.OWNER,
        )

    def _membership(self, *, username: str, permissions: tuple[str, ...], role=AccessRole.CUSTOM):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(
            company=self.company,
            key=f"custom-{username}",
            name=f"{username} profile",
            is_system=False,
            is_active=True,
        )
        AccessProfilePermission.objects.bulk_create(
            AccessProfilePermission(profile=profile, permission=permission)
            for permission in permissions
        )
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=role,
            access_profile=profile,
        )
        return user, membership

    def test_owner_is_the_only_builtin_profile_with_automatic_sourcing_authority(self):
        owner_permissions = permissions_for_legacy_role(AccessRole.OWNER)
        self.assertIn(AccessPermission.SOURCING_VENDORS_MANAGE, owner_permissions)
        self.assertIn(AccessPermission.SOURCING_MANPOWER_MANAGE, owner_permissions)
        self.assertIn(AccessPermission.SOURCING_MASTERS_MANAGE, owner_permissions)

        for role in (
            AccessRole.OPERATIONS_ADMIN,
            AccessRole.ACCESS_ADMINISTRATOR,
            AccessRole.INVENTORY_MANAGER,
            AccessRole.STOREKEEPER,
            AccessRole.FINANCE_MANAGER,
            AccessRole.INTERNAL_PAYROLL_OFFICER,
            AccessRole.RENTAL_MANPOWER_OFFICER,
            AccessRole.RENTAL_SUPERVISOR,
            AccessRole.FINANCE_REVIEWER,
            AccessRole.READ_ONLY_AUDITOR,
        ):
            self.assertFalse(any(permission.value.startswith("sourcing.") for permission in permissions_for_legacy_role(role)))

    def test_vendor_viewer_has_vendor_module_without_manpower_or_edit_authority(self):
        user, membership = self._membership(
            username="vendor-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        self.assertTrue(membership_can_module(membership, PlatformModule.SOURCING))
        self.assertTrue(membership_can_view_vendor_sourcing(membership))
        self.assertFalse(membership_can_manage_vendor_sourcing(membership))
        self.assertFalse(membership_can_view_manpower_sourcing(membership))

        self.client.force_login(user)
        response = self.client.get(reverse("sourcing:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["SOURCING_ACCESS"]["vendors"]["view"])
        self.assertFalse(response.context["SOURCING_ACCESS"]["vendors"]["manage"])
        self.assertFalse(response.context["SOURCING_ACCESS"]["manpower"]["view"])
        module_keys = [item["key"] for item in response.context["PLATFORM_CONTEXT"]["modules"]]
        self.assertIn("sourcing", module_keys)
        self.assertNotIn("inventory", module_keys)
        self.assertNotIn("payroll", module_keys)

    def test_manpower_editor_does_not_gain_vendor_access(self):
        _user, membership = self._membership(
            username="manpower-editor",
            permissions=(
                AccessPermission.SOURCING_MANPOWER_VIEW.value,
                AccessPermission.SOURCING_MANPOWER_MANAGE.value,
            ),
        )
        self.assertTrue(membership_can_view_manpower_sourcing(membership))
        self.assertTrue(membership_can_manage_manpower_sourcing(membership))
        self.assertFalse(membership_can_view_vendor_sourcing(membership))
        self.assertFalse(membership_can_manage_vendor_sourcing(membership))

    def test_operational_storekeeper_does_not_inherit_sourcing(self):
        User = get_user_model()
        user = User.objects.create_user(username="storekeeper-no-sourcing", password="strong-test-password")
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.STOREKEEPER,
        )
        self.assertFalse(membership_can_module(membership, PlatformModule.SOURCING))
        self.client.force_login(user)
        response = self.client.get(reverse("sourcing:home"))
        self.assertEqual(response.status_code, 403)

    def test_manage_permissions_require_matching_view_permission(self):
        with self.assertRaises(ValidationError):
            _clean_permissions([AccessPermission.SOURCING_VENDORS_MANAGE.value])
        cleaned = _clean_permissions([
            AccessPermission.SOURCING_VENDORS_VIEW.value,
            AccessPermission.SOURCING_VENDORS_MANAGE.value,
        ])
        self.assertIn(AccessPermission.SOURCING_VENDORS_MANAGE.value, cleaned)

    def test_export_requires_at_least_one_sourcing_view_permission(self):
        with self.assertRaises(ValidationError):
            _clean_permissions([AccessPermission.SOURCING_EXPORT_EXECUTE.value])
        cleaned = _clean_permissions([
            AccessPermission.SOURCING_MANPOWER_VIEW.value,
            AccessPermission.SOURCING_EXPORT_EXECUTE.value,
        ])
        self.assertIn(AccessPermission.SOURCING_EXPORT_EXECUTE.value, cleaned)

    def test_permission_catalog_exposes_sourcing_as_a_separate_category(self):
        rows = [row for row in permission_catalog() if row["code"].startswith("sourcing.")]
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row["category"] == "Sourcing Directory" for row in rows))
        by_code = {row["code"]: row for row in rows}
        self.assertEqual(by_code[AccessPermission.SOURCING_VENDORS_VIEW.value]["kind"], "view")
        self.assertEqual(by_code[AccessPermission.SOURCING_VENDORS_MANAGE.value]["kind"], "action")
