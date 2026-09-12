from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import (
    membership_can_edit,
    membership_can_workspace,
    membership_has_capability,
)
from apps.accounts.roles import AccessRole, Capability, Workspace
from apps.accounts.selectors import ACTIVE_COMPANY_SESSION_KEY
from apps.accounts.services import change_membership_role, set_membership_active
from apps.core.models import AuditEvent, Company


class CompanyContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="operator", password="strong-test-password")
        self.company = Company.objects.create(name="Acme Contracting", slug="acme-contracting")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.STOREKEEPER,
        )

    def test_authenticated_request_resolves_company_membership(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.company, self.company)
        self.assertEqual(response.wsgi_request.company_membership, self.membership)
        self.assertEqual(self.client.session[ACTIVE_COMPANY_SESSION_KEY], str(self.company.id))

    @override_settings(SINGLE_COMPANY_MODE=False)
    def test_company_switch_rejects_company_without_membership(self):
        other_company = Company.objects.create(name="Other Company", slug="other-company")
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:activate-company", args=[other_company.id]))
        self.assertEqual(response.status_code, 403)

    @override_settings(SINGLE_COMPANY_MODE=False)
    def test_company_switch_sets_session_for_authorized_company(self):
        second_company = Company.objects.create(name="Second Company", slug="second-company")
        CompanyMembership.objects.create(
            company=second_company,
            user=self.user,
            role=AccessRole.INVENTORY_MANAGER,
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:activate-company", args=[second_company.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session[ACTIVE_COMPANY_SESSION_KEY], str(second_company.id))


    def test_single_company_mode_ignores_session_company_switching(self):
        other_company = Company.objects.create(name="Other Company", slug="other-company")
        CompanyMembership.objects.create(company=other_company, user=self.user, role=AccessRole.INVENTORY_MANAGER)
        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_COMPANY_SESSION_KEY] = str(other_company.id)
        session.save()
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.wsgi_request.company, self.company)

    def test_single_company_mode_rejects_activate_company_endpoint(self):
        second_company = Company.objects.create(name="Second Company", slug="second-company")
        CompanyMembership.objects.create(company=second_company, user=self.user, role=AccessRole.INVENTORY_MANAGER)
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:activate-company", args=[second_company.id]))
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_is_not_selected(self):
        self.membership.is_active = False
        self.membership.save(update_fields=("is_active", "updated_at"))
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertIsNone(response.wsgi_request.company)
        self.assertIsNone(response.wsgi_request.company_membership)


class UnifiedRolePolicyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Policy Co", slug="policy-co")
        self.user = User.objects.create_user(username="policy-user")

    def membership(self, role):
        return CompanyMembership(company=self.company, user=self.user, role=role, is_active=True)

    def test_storekeeper_can_edit_inventory_but_not_manage_or_import(self):
        membership = self.membership(AccessRole.STOREKEEPER)
        self.assertTrue(membership_can_workspace(membership, Workspace.INVENTORY))
        self.assertTrue(membership_can_edit(membership, Workspace.INVENTORY))
        self.assertTrue(membership_has_capability(membership, Capability.EDIT_INVENTORY))
        self.assertFalse(membership_has_capability(membership, Capability.MANAGE_INVENTORY))
        self.assertFalse(membership_has_capability(membership, Capability.IMPORT_INVENTORY))
        self.assertFalse(membership_can_workspace(membership, Workspace.INTERNAL))

    def test_operations_admin_does_not_gain_payroll_or_payment_authority(self):
        membership = self.membership(AccessRole.OPERATIONS_ADMIN)
        self.assertTrue(membership_has_capability(membership, Capability.MANAGE_INVENTORY))
        self.assertTrue(membership_has_capability(membership, Capability.IMPORT_INVENTORY))
        self.assertFalse(membership_can_workspace(membership, Workspace.INTERNAL))
        self.assertFalse(membership_can_workspace(membership, Workspace.RENTAL))
        self.assertFalse(membership_has_capability(membership, Capability.APPROVE))
        self.assertFalse(membership_has_capability(membership, Capability.PAY))
        self.assertFalse(membership_has_capability(membership, Capability.MANAGE_ACCESS))

    def test_owner_has_cross_module_authority(self):
        membership = self.membership(AccessRole.OWNER)
        for workspace in Workspace:
            self.assertTrue(membership_can_workspace(membership, workspace))
        for capability in Capability:
            self.assertTrue(membership_has_capability(membership, capability))

    def test_finance_manager_cannot_mutate_inventory(self):
        membership = self.membership(AccessRole.FINANCE_MANAGER)
        self.assertTrue(membership_can_workspace(membership, Workspace.INTERNAL))
        self.assertTrue(membership_can_workspace(membership, Workspace.RENTAL))
        self.assertTrue(membership_has_capability(membership, Capability.PAY))
        self.assertFalse(membership_can_workspace(membership, Workspace.INVENTORY))
        self.assertFalse(membership_has_capability(membership, Capability.EDIT_INVENTORY))


class OwnerProtectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Owner Co", slug="owner-co")
        self.owner = User.objects.create_user(username="owner")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner,
            role=AccessRole.OWNER,
        )

    def test_last_active_owner_cannot_be_demoted(self):
        with self.assertRaises(ValidationError):
            change_membership_role(
                actor_membership=self.membership,
                membership_id=self.membership.id,
                role=AccessRole.OPERATIONS_ADMIN,
            )

    def test_last_active_owner_cannot_be_deactivated(self):
        with self.assertRaises(ValidationError):
            set_membership_active(
                actor_membership=self.membership,
                membership_id=self.membership.id,
                is_active=False,
            )

    def test_owner_role_change_is_audited_when_another_owner_exists(self):
        User = get_user_model()
        second = User.objects.create_user(username="owner-two")
        CompanyMembership.objects.create(company=self.company, user=second, role=AccessRole.OWNER)

        change_membership_role(
            actor_membership=self.membership,
            membership_id=self.membership.id,
            role=AccessRole.OPERATIONS_ADMIN,
        )

        event = AuditEvent.objects.get(action="access.membership.role_changed")
        self.assertEqual(event.actor_id, self.owner.id)
        self.assertEqual(event.actor_membership_id, self.membership.id)
        self.assertEqual(event.before["role"], AccessRole.OWNER)
        self.assertEqual(event.after["role"], AccessRole.OPERATIONS_ADMIN)

    def test_non_access_manager_cannot_change_role(self):
        User = get_user_model()
        store_user = User.objects.create_user(username="store-user")
        store_membership = CompanyMembership.objects.create(
            company=self.company,
            user=store_user,
            role=AccessRole.STOREKEEPER,
        )
        with self.assertRaises(PermissionDenied):
            change_membership_role(
                actor_membership=store_membership,
                membership_id=self.membership.id,
                role=AccessRole.OPERATIONS_ADMIN,
            )
