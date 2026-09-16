from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import create_access_profile, update_access_profile
from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.accounts.security import SESSION_SECURITY_VERSION_KEY
from apps.accounts.user_management import create_managed_user, set_managed_user_active, update_managed_user
from apps.core.models import AuditEvent, Company


class SessionSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Session Security Co", slug="session-security-co")
        self.owner_user = User.objects.create_user(username="security-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.user = User.objects.create_user(username="security-user", password="UserPass!2026")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.STOREKEEPER,
        )

    def _stamped_client(self) -> Client:
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.session[SESSION_SECURITY_VERSION_KEY], self.user.security_version)
        return client

    def test_pre_upgrade_session_is_stamped_on_first_request(self):
        client = Client()
        client.force_login(self.user)
        session = client.session
        session.pop(SESSION_SECURITY_VERSION_KEY, None)
        session.save()
        response = client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(client.session[SESSION_SECURITY_VERSION_KEY], self.user.security_version)

    def test_access_profile_change_revokes_existing_session_on_next_request(self):
        client = self._stamped_client()
        inventory_manager = self.company.access_profiles.get(key="role-inventory-manager")
        old_version = self.user.security_version
        update_managed_user(
            actor_membership=self.owner,
            membership_id=self.membership.pk,
            payload={"accessProfileId": str(inventory_manager.pk)},
        )
        self.user.refresh_from_db()
        self.assertGreater(self.user.security_version, old_version)
        response = client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_scope_change_revokes_api_session_with_explicit_401(self):
        client = self._stamped_client()
        update_managed_user(
            actor_membership=self.owner,
            membership_id=self.membership.pk,
            payload={
                "scopes": {
                    "projectMode": "none", "projectIds": [],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                }
            },
        )
        response = client.get(reverse("accounts:access-users-api"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "session_revoked")

    def test_custom_profile_permission_edit_revokes_every_assigned_user_session(self):
        profile = create_access_profile(
            actor_membership=self.owner,
            payload={
                "name": "Inventory Viewer",
                "permissions": [AccessPermission.INVENTORY_DASHBOARD_VIEW.value],
            },
        )
        self.membership.access_profile = profile
        self.membership.role = AccessRole.CUSTOM
        self.membership.save(update_fields=("access_profile", "role", "updated_at"))
        client = self._stamped_client()
        old_version = self.user.security_version
        update_access_profile(
            actor_membership=self.owner,
            profile_id=profile.pk,
            payload={
                "permissions": [
                    AccessPermission.INVENTORY_DASHBOARD_VIEW.value,
                    AccessPermission.INVENTORY_STOCK_VIEW.value,
                ]
            },
        )
        self.user.refresh_from_db()
        self.assertGreater(self.user.security_version, old_version)
        response = client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_deactivate_then_reactivate_before_next_request_still_revokes_old_session(self):
        client = self._stamped_client()
        set_managed_user_active(
            actor_membership=self.owner,
            membership_id=self.membership.pk,
            is_active=False,
        )
        set_managed_user_active(
            actor_membership=self.owner,
            membership_id=self.membership.pk,
            is_active=True,
        )
        response = client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))

    def test_temporary_password_blocks_operations_until_changed(self):
        store_profile = self.company.access_profiles.get(key="role-storekeeper")
        temp_membership = create_managed_user(
            actor_membership=self.owner,
            payload={
                "username": "temporary-user",
                "email": "temporary-user@example.test",
                "firstName": "Temporary",
                "lastName": "User",
                "temporaryPassword": "Temporary!Pass2026",
                "accessProfileId": str(store_profile.pk),
                "scopes": {
                    "projectMode": "all", "projectIds": [],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                },
            },
        )
        client = Client()
        client.force_login(temp_membership.user)
        page = client.get(reverse("core:dashboard"))
        self.assertRedirects(page, reverse("accounts:change-password"))
        api = client.get(reverse("accounts:access-users-api"))
        self.assertEqual(api.status_code, 428)
        self.assertEqual(api.json()["code"], "password_change_required")

        changed = client.post(
            reverse("accounts:change-password"),
            data={
                "old_password": "Temporary!Pass2026",
                "new_password1": "Permanent!Pass2026-New",
                "new_password2": "Permanent!Pass2026-New",
            },
        )
        self.assertEqual(changed.status_code, 302)
        self.assertEqual(changed.url, reverse("accounts:home"))
        temp_membership.user.refresh_from_db()
        self.assertFalse(temp_membership.user.must_change_password)
        self.assertEqual(client.session[SESSION_SECURITY_VERSION_KEY], temp_membership.user.security_version)
        self.assertTrue(AuditEvent.objects.filter(action="access.user.password_changed").exists())
