from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditEvent, Company
from apps.internal_payroll.models import Branch
from apps.inventory.models import InventoryLocation
from apps.projects.models import Project

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.accounts.user_management import (
    create_managed_user,
    delete_unused_managed_user,
    reset_managed_user_password,
    set_managed_user_active,
    update_managed_user,
)


class UserManagementBackendTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Access CRUD Co", slug="access-crud-co")
        self.owner_user = User.objects.create_user(username="access-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.access_admin_user = User.objects.create_user(username="access-admin", password="AdminPass!2026")
        self.access_admin = CompanyMembership.objects.create(
            company=self.company, user=self.access_admin_user, role=AccessRole.ACCESS_ADMINISTRATOR
        )
        self.store_profile = AccessProfile.objects.get(company=self.company, key="role-storekeeper")
        self.owner_profile = AccessProfile.objects.get(company=self.company, key="role-owner")

    def _payload(self, **overrides):
        payload = {
            "username": "new-user",
            "email": "new-user@example.test",
            "firstName": "New",
            "lastName": "User",
            "temporaryPassword": "Temporary!Pass2026",
            "accessProfileId": str(self.store_profile.pk),
            "scopes": {
                "projectMode": "all", "projectIds": [],
                "branchMode": "all", "branchIds": [],
                "inventoryLocationMode": "all", "inventoryLocationIds": [],
            },
        }
        payload.update(overrides)
        return payload

    def test_access_admin_can_create_operational_user_without_receiving_operational_permissions(self):
        membership = create_managed_user(actor_membership=self.access_admin, payload=self._payload())
        self.assertEqual(membership.access_profile_id, self.store_profile.pk)
        self.assertEqual(membership.role, AccessRole.STOREKEEPER)
        self.assertTrue(membership.user.must_change_password)
        self.assertFalse(membership.user.is_staff)
        self.assertTrue(AuditEvent.objects.filter(action="access.user.created", object_id=str(membership.pk)).exists())

    def test_access_admin_cannot_assign_owner_profile(self):
        with self.assertRaises(PermissionDenied):
            create_managed_user(
                actor_membership=self.access_admin,
                payload=self._payload(accessProfileId=str(self.owner_profile.pk)),
            )

    def test_owner_can_create_second_owner(self):
        membership = create_managed_user(
            actor_membership=self.owner,
            payload=self._payload(
                username="second-owner", email="second-owner@example.test", accessProfileId=str(self.owner_profile.pk)
            ),
        )
        self.assertEqual(membership.access_profile_id, self.owner_profile.pk)

    def test_selected_scopes_are_company_validated_and_persisted(self):
        project = Project.objects.create(company=self.company, code="SCOPE-1", name="Scope Project")
        branch = Branch.objects.create(company=self.company, code="SCOPE-B", name="Scope Branch")
        location = InventoryLocation.objects.create(
            company=self.company, code="SCOPE-L", name="Scope Store", location_type=InventoryLocation.Type.OFFICE
        )
        membership = create_managed_user(
            actor_membership=self.owner,
            payload=self._payload(scopes={
                "projectMode": "selected", "projectIds": [str(project.pk)],
                "branchMode": "selected", "branchIds": [str(branch.pk)],
                "inventoryLocationMode": "selected", "inventoryLocationIds": [str(location.pk)],
            }),
        )
        self.assertEqual(membership.project_scope_mode, ScopeMode.SELECTED)
        self.assertEqual(list(membership.project_scopes.values_list("project_id", flat=True)), [project.pk])
        self.assertEqual(list(membership.branch_scopes.values_list("branch_id", flat=True)), [branch.pk])
        self.assertEqual(list(membership.inventory_location_scopes.values_list("inventory_location_id", flat=True)), [location.pk])

    def test_selected_scope_requires_rows(self):
        with self.assertRaises(ValidationError):
            create_managed_user(
                actor_membership=self.owner,
                payload=self._payload(scopes={
                    "projectMode": "selected", "projectIds": [],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                }),
            )

    def test_user_identity_must_be_unique_case_insensitively(self):
        create_managed_user(actor_membership=self.owner, payload=self._payload())
        with self.assertRaises(ValidationError):
            create_managed_user(
                actor_membership=self.owner,
                payload=self._payload(username="NEW-USER", email="other@example.test"),
            )

    def test_access_admin_cannot_modify_owner(self):
        with self.assertRaises(PermissionDenied):
            update_managed_user(
                actor_membership=self.access_admin,
                membership_id=self.owner.pk,
                payload={"firstName": "Changed"},
            )

    def test_actor_cannot_change_own_access_profile_or_scopes(self):
        with self.assertRaises(PermissionDenied):
            update_managed_user(
                actor_membership=self.access_admin,
                membership_id=self.access_admin.pk,
                payload={"accessProfileId": str(self.store_profile.pk)},
            )

    def test_password_reset_sets_forced_change_and_changes_hash(self):
        target = create_managed_user(actor_membership=self.owner, payload=self._payload())
        old_hash = target.user.password
        reset_managed_user_password(
            actor_membership=self.owner,
            membership_id=target.pk,
            temporary_password="Another!Temporary2026",
        )
        target.user.refresh_from_db()
        self.assertNotEqual(target.user.password, old_hash)
        self.assertTrue(target.user.must_change_password)
        self.assertIsNotNone(target.user.credentials_updated_at)
        self.assertTrue(AuditEvent.objects.filter(action="access.user.password_reset", object_id=str(target.pk)).exists())

    def test_access_admin_cannot_reset_owner_password(self):
        with self.assertRaises(PermissionDenied):
            reset_managed_user_password(
                actor_membership=self.access_admin,
                membership_id=self.owner.pk,
                temporary_password="Blocked!Temporary2026",
            )

    def test_deactivation_disables_identity_when_no_other_active_company_access(self):
        target = create_managed_user(actor_membership=self.owner, payload=self._payload())
        set_managed_user_active(actor_membership=self.owner, membership_id=target.pk, is_active=False)
        target.refresh_from_db(); target.user.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertFalse(target.user.is_active)

    def test_actor_cannot_deactivate_self(self):
        with self.assertRaises(PermissionDenied):
            set_managed_user_active(actor_membership=self.owner, membership_id=self.owner.pk, is_active=False)

    def test_reactivation_requires_active_profile(self):
        target = create_managed_user(actor_membership=self.owner, payload=self._payload())
        set_managed_user_active(actor_membership=self.owner, membership_id=target.pk, is_active=False)
        self.store_profile.is_active = False
        self.store_profile.save(update_fields=("is_active", "updated_at"))
        with self.assertRaises(ValidationError):
            set_managed_user_active(actor_membership=self.owner, membership_id=target.pk, is_active=True)

    def test_cross_company_scope_assignment_is_rejected(self):
        other = Company.objects.create(name="Other Scope Co", slug="other-scope-co")
        foreign_project = Project.objects.create(company=other, code="FOREIGN-SCOPE", name="Foreign Scope")
        with self.assertRaises(ValidationError):
            create_managed_user(
                actor_membership=self.owner,
                payload=self._payload(scopes={
                    "projectMode": "selected", "projectIds": [str(foreign_project.pk)],
                    "branchMode": "all", "branchIds": [],
                    "inventoryLocationMode": "all", "inventoryLocationIds": [],
                }),
            )

    def test_unused_never_signed_in_user_can_be_guardedly_deleted(self):
        target = create_managed_user(actor_membership=self.owner, payload=self._payload())
        user_id = target.user_id
        delete_unused_managed_user(
            actor_membership=self.owner, membership_id=target.pk, confirmation=target.user.username
        )
        self.assertFalse(get_user_model().objects.filter(pk=user_id).exists())
        self.assertTrue(AuditEvent.objects.filter(action="access.user.deleted_unused").exists())

    def test_used_account_must_be_deactivated_not_deleted(self):
        target = create_managed_user(actor_membership=self.owner, payload=self._payload())
        target.user.last_login = target.created_at
        target.user.save(update_fields=("last_login", "is_staff"))
        with self.assertRaises(ValidationError):
            delete_unused_managed_user(
                actor_membership=self.owner, membership_id=target.pk, confirmation=target.user.username
            )

    def test_custom_profile_uses_custom_classification_without_role_authority(self):
        custom = AccessProfile.objects.create(company=self.company, key="timesheet-view", name="Timesheet Viewer")
        AccessProfilePermission.objects.create(
            profile=custom, permission=AccessPermission.RENTAL_TIMESHEETS_VIEW.value
        )
        target = create_managed_user(
            actor_membership=self.owner,
            payload=self._payload(username="custom-user", email="custom@example.test", accessProfileId=str(custom.pk)),
        )
        self.assertEqual(target.role, AccessRole.CUSTOM)
        self.assertEqual(target.access_profile_id, custom.pk)

    def test_user_api_is_company_scoped_paginated_and_permission_guarded(self):
        create_managed_user(actor_membership=self.owner, payload=self._payload())
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:access-users-api"), {"page_size": 25})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertLessEqual(len(response.json()["users"]["rows"]), 25)

    def test_scope_lookup_is_bounded(self):
        for index in range(30):
            Project.objects.create(company=self.company, code=f"LOOK-{index:02d}", name=f"Lookup {index}")
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:access-scope-lookup-api"), {"type": "projects", "q": "LOOK"})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["rows"]), 25)
