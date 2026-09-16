from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission, permissions_for_legacy_role, system_profile_key_for_role
from apps.accounts.access_policy import (
    effective_access_for_membership,
    membership_allows_branch,
    membership_allows_inventory_location,
    membership_allows_project,
    membership_has_permission,
)
from apps.accounts.models import (
    AccessProfile,
    AccessProfilePermission,
    CompanyMembership,
    MembershipBranchScope,
    MembershipInventoryLocationScope,
    MembershipProjectScope,
    ScopeMode,
)
from apps.accounts.roles import AccessRole
from apps.accounts.services import change_membership_role, create_company_membership
from apps.core.models import Company
from apps.internal_payroll.models import Branch
from apps.inventory.models import InventoryLocation
from apps.projects.models import Project


class GranularAccessFoundationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Access Co", slug="access-co")
        self.owner_user = User.objects.create_user(username="owner-access", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner_user,
            role=AccessRole.OWNER,
        )

    def _profile(self, *, key="custom-test", permissions=()):
        profile = AccessProfile.objects.create(
            company=self.company,
            key=key,
            name=key.replace("-", " ").title(),
        )
        AccessProfilePermission.objects.bulk_create(
            [AccessProfilePermission(profile=profile, permission=value) for value in permissions]
        )
        return profile

    def test_system_profile_provisioning_preserves_existing_role_permissions(self):
        expected = {permission.value for permission in permissions_for_legacy_role(AccessRole.STOREKEEPER)}
        access = effective_access_for_membership(self.owner)
        self.assertIsNotNone(access)
        self.assertIn(AccessPermission.ACCESS_USERS_MANAGE.value, access.permissions)

        User = get_user_model()
        store_user = User.objects.create_user(username="store-profile")
        store = CompanyMembership.objects.create(
            company=self.company,
            user=store_user,
            role=AccessRole.STOREKEEPER,
        )
        access = effective_access_for_membership(store)
        self.assertEqual(access.permissions, frozenset(expected))
        self.assertTrue(membership_has_permission(store, AccessPermission.INVENTORY_STOCK_RECEIVE))
        self.assertFalse(membership_has_permission(store, AccessPermission.INVENTORY_STOCK_ADJUST))

    def test_profile_permissions_are_authoritative_for_granular_policy(self):
        profile = self._profile(
            permissions=(AccessPermission.RENTAL_TIMESHEETS_VIEW.value, AccessPermission.RENTAL_TIMESHEETS_EDIT.value)
        )
        User = get_user_model()
        user = User.objects.create_user(username="custom-policy")
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
            access_profile=profile,
        )
        self.assertTrue(membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_VIEW))
        self.assertTrue(membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_EDIT))
        self.assertFalse(membership_has_permission(membership, AccessPermission.RENTAL_WORKERS_MANAGE))

    def test_inactive_assigned_profile_fails_closed_instead_of_falling_back_to_role(self):
        profile = self._profile(permissions=(AccessPermission.RENTAL_WORKERS_MANAGE.value,))
        profile.is_active = False
        profile.save(update_fields=("is_active", "updated_at"))
        User = get_user_model()
        user = User.objects.create_user(username="inactive-profile")
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
            access_profile=profile,
        )
        access = effective_access_for_membership(membership)
        self.assertEqual(access.permissions, frozenset())
        self.assertFalse(membership_has_permission(membership, AccessPermission.RENTAL_WORKERS_MANAGE))

    def test_effective_access_is_cached_on_membership_instance(self):
        profile = self._profile(permissions=(AccessPermission.INVENTORY_STOCK_VIEW.value,))
        self.owner.access_profile = profile
        self.owner.save(update_fields=("access_profile", "updated_at"))
        first = effective_access_for_membership(self.owner)
        with self.assertNumQueries(0):
            second = effective_access_for_membership(self.owner)
        self.assertIs(first, second)

    def test_create_membership_assigns_system_profile_with_equivalent_permissions(self):
        User = get_user_model()
        worker = User.objects.create_user(username="new-storekeeper")
        membership = create_company_membership(
            actor_membership=self.owner,
            user=worker,
            role=AccessRole.STOREKEEPER,
        )
        self.assertIsNotNone(membership.access_profile_id)
        self.assertEqual(membership.access_profile.key, system_profile_key_for_role(AccessRole.STOREKEEPER))
        self.assertTrue(membership.access_profile.is_system)
        actual = set(membership.access_profile.permission_grants.values_list("permission", flat=True))
        expected = {permission.value for permission in permissions_for_legacy_role(AccessRole.STOREKEEPER)}
        self.assertEqual(actual, expected)

    def test_role_change_keeps_compatibility_profile_in_sync(self):
        User = get_user_model()
        worker = User.objects.create_user(username="role-sync")
        membership = create_company_membership(
            actor_membership=self.owner,
            user=worker,
            role=AccessRole.STOREKEEPER,
        )
        changed = change_membership_role(
            actor_membership=self.owner,
            membership_id=membership.id,
            role=AccessRole.INVENTORY_MANAGER,
        )
        self.assertEqual(changed.role, AccessRole.INVENTORY_MANAGER)
        self.assertEqual(changed.access_profile.key, system_profile_key_for_role(AccessRole.INVENTORY_MANAGER))

    def test_role_classification_cannot_override_assigned_profile(self):
        profile = self._profile(permissions=(AccessPermission.RENTAL_TIMESHEETS_VIEW.value,))
        User = get_user_model()
        user = User.objects.create_user(username="role-is-metadata")
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.OWNER, access_profile=profile
        )
        self.assertTrue(membership_has_permission(membership, AccessPermission.RENTAL_TIMESHEETS_VIEW))
        self.assertFalse(membership_has_permission(membership, AccessPermission.ACCESS_USERS_MANAGE))

    def test_missing_profile_fails_closed_without_role_fallback(self):
        User = get_user_model()
        user = User(username="unsaved-missing-profile")
        membership = CompanyMembership(
            company=self.company, user=user, role=AccessRole.OWNER, access_profile=None, is_active=True
        )
        access = effective_access_for_membership(membership)
        self.assertEqual(access.permissions, frozenset())
        self.assertEqual(access.profile_key, "missing-profile")

    def test_profile_must_belong_to_membership_company(self):
        other = Company.objects.create(name="Other Access Co", slug="other-access-co")
        other_profile = AccessProfile.objects.create(company=other, key="other", name="Other")
        self.owner.access_profile = other_profile
        with self.assertRaises(ValidationError):
            self.owner.save()

    def test_unknown_permission_is_rejected(self):
        profile = self._profile()
        with self.assertRaises(ValidationError):
            AccessProfilePermission.objects.create(profile=profile, permission="inventory.superuser.everything")

    def test_selected_scopes_allow_only_explicit_company_records(self):
        project = Project.objects.create(company=self.company, code="P-1", name="Project 1")
        other_project = Project.objects.create(company=self.company, code="P-2", name="Project 2")
        branch = Branch.objects.create(company=self.company, code="B1", name="Branch 1")
        other_branch = Branch.objects.create(company=self.company, code="B2", name="Branch 2")
        location = InventoryLocation.objects.create(
            company=self.company,
            code="STORE-1",
            name="Main Store",
            location_type=InventoryLocation.Type.OFFICE,
        )
        other_location = InventoryLocation.objects.create(
            company=self.company,
            code="STORE-2",
            name="Second Store",
            location_type=InventoryLocation.Type.OFFICE,
        )
        self.owner.project_scope_mode = ScopeMode.SELECTED
        self.owner.branch_scope_mode = ScopeMode.SELECTED
        self.owner.inventory_location_scope_mode = ScopeMode.SELECTED
        self.owner.save(update_fields=(
            "project_scope_mode", "branch_scope_mode", "inventory_location_scope_mode", "updated_at"
        ))
        MembershipProjectScope.objects.create(membership=self.owner, project=project)
        MembershipBranchScope.objects.create(membership=self.owner, branch=branch)
        MembershipInventoryLocationScope.objects.create(membership=self.owner, inventory_location=location)

        self.assertTrue(membership_allows_project(self.owner, project))
        self.assertFalse(membership_allows_project(self.owner, other_project))
        self.assertTrue(membership_allows_branch(self.owner, branch))
        self.assertFalse(membership_allows_branch(self.owner, other_branch))
        self.assertTrue(membership_allows_inventory_location(self.owner, location))
        self.assertFalse(membership_allows_inventory_location(self.owner, other_location))

    def test_scope_record_rejects_cross_company_assignment(self):
        other = Company.objects.create(name="Scope Other", slug="scope-other")
        foreign_project = Project.objects.create(company=other, code="FOREIGN", name="Foreign")
        with self.assertRaises(ValidationError):
            MembershipProjectScope.objects.create(membership=self.owner, project=foreign_project)

    def test_request_exposes_effective_access_snapshot(self):
        profile = self._profile(permissions=(AccessPermission.INVENTORY_DASHBOARD_VIEW.value,))
        self.owner.access_profile = profile
        self.owner.save(update_fields=("access_profile", "updated_at"))
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        snapshot = response.wsgi_request.effective_access
        self.assertEqual(snapshot.profile_key, profile.key)
        self.assertEqual(snapshot.permissions, frozenset({AccessPermission.INVENTORY_DASHBOARD_VIEW.value}))
        self.assertEqual(snapshot.project_scope_mode, ScopeMode.ALL)
