from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_history import access_history_page, user_access_history
from apps.accounts.models import CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.accounts.user_management import create_managed_user, restore_managed_user_access, update_managed_user
from apps.core.models import AuditEvent, Company


class AccessHistoryRecoveryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Access History Co", slug="access-history-co")
        self.owner_user = User.objects.create_user(username="history-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.store_profile = self.company.access_profiles.get(key="role-storekeeper")
        self.inventory_manager_profile = self.company.access_profiles.get(key="role-inventory-manager")
        self.target = create_managed_user(
            actor_membership=self.owner,
            payload={
                "username": "history-user",
                "email": "history-user@example.test",
                "firstName": "History",
                "lastName": "User",
                "temporaryPassword": "Temporary!Pass2026",
                "accessProfileId": str(self.store_profile.pk),
                "scopes": {
                    "projectMode": "all", "projectIds": [],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                },
            },
        )

    def test_access_history_is_company_scoped_and_permission_guarded(self):
        page = access_history_page(actor_membership=self.owner, page_size=25)
        self.assertGreaterEqual(len(page["rows"]), 1)
        self.assertTrue(all(row["targetType"].startswith("accounts.") for row in page["rows"]))

        outsider_user = get_user_model().objects.create_user(username="history-store", password="StorePass!2026")
        outsider = CompanyMembership.objects.create(company=self.company, user=outsider_user, role=AccessRole.STOREKEEPER)
        with self.assertRaises(PermissionDenied):
            access_history_page(actor_membership=outsider)

    def test_user_history_marks_only_recoverable_before_snapshots(self):
        update_managed_user(
            actor_membership=self.owner,
            membership_id=self.target.pk,
            payload={
                "accessProfileId": str(self.inventory_manager_profile.pk),
                "scopes": {
                    "projectMode": "none", "projectIds": [],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                },
            },
        )
        history = user_access_history(actor_membership=self.owner, membership_id=self.target.pk)
        updated = next(row for row in history["rows"] if row["action"] == "access.user.updated")
        created = next(row for row in history["rows"] if row["action"] == "access.user.created")
        self.assertTrue(updated["restorableBefore"])
        self.assertFalse(created["restorableBefore"])

    def test_restore_reapplies_prior_profile_and_scope_and_revokes_sessions(self):
        old_version = self.target.user.security_version
        update_managed_user(
            actor_membership=self.owner,
            membership_id=self.target.pk,
            payload={
                "accessProfileId": str(self.inventory_manager_profile.pk),
                "scopes": {
                    "projectMode": "none", "projectIds": [],
                    "branchMode": "none", "branchIds": [],
                    "inventoryLocationMode": "none", "inventoryLocationIds": [],
                },
            },
        )
        event = AuditEvent.objects.filter(
            company=self.company,
            action="access.user.updated",
            object_id=str(self.target.pk),
        ).latest("created_at")

        restored = restore_managed_user_access(
            actor_membership=self.owner,
            membership_id=self.target.pk,
            event_id=event.pk,
            confirmation=self.target.user.username,
        )
        restored.refresh_from_db()
        restored.user.refresh_from_db()
        self.assertEqual(restored.access_profile_id, self.store_profile.pk)
        self.assertEqual(restored.project_scope_mode, ScopeMode.ALL)
        self.assertEqual(restored.branch_scope_mode, ScopeMode.ALL)
        self.assertEqual(restored.inventory_location_scope_mode, ScopeMode.ALL)
        self.assertGreater(restored.user.security_version, old_version)
        recovery = AuditEvent.objects.get(action="access.user.access_restored", object_id=str(self.target.pk))
        self.assertEqual(recovery.metadata["sourceEventId"], str(event.pk))
        self.assertTrue(recovery.metadata["sessionsInvalidated"])

    def test_restore_requires_exact_username_confirmation(self):
        update_managed_user(
            actor_membership=self.owner,
            membership_id=self.target.pk,
            payload={"accessProfileId": str(self.inventory_manager_profile.pk)},
        )
        event = AuditEvent.objects.filter(action="access.user.updated", object_id=str(self.target.pk)).latest("created_at")
        with self.assertRaises(ValidationError):
            restore_managed_user_access(
                actor_membership=self.owner,
                membership_id=self.target.pk,
                event_id=event.pk,
                confirmation="wrong-user",
            )

    def test_access_history_api_and_user_history_api(self):
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:access-audit-api"), {"page_size": 25})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        user_response = self.client.get(reverse("accounts:access-user-history-api", args=[self.target.pk]))
        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(user_response.json()["history"]["membershipId"], str(self.target.pk))
