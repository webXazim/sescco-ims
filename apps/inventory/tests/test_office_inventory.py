"""Regression coverage for Office Stock navigation and access scoping."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, MembershipInventoryLocationScope, User
from apps.accounts.roles import AccessRole, ScopeMode
from apps.core.models import Company
from apps.inventory.models import InventoryLocation


class OfficeInventoryAvailabilityTests(TestCase):
    def setUp(self):
        # A new company is not guaranteed to have the legacy migration's office.
        self.company = Company.objects.create(name="Office Regression", slug="office-regression")
        self.user = User.objects.create_user(username="office-regression-user", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company, user=self.user, role=AccessRole.OWNER
        )
        self.client.force_login(self.user)
        self.url = reverse("inventory:office")

    def create_office(self, code="OFFICE-A", **overrides):
        return InventoryLocation.objects.create(
            company=self.company,
            code=code,
            name="Main Office",
            location_type=InventoryLocation.Type.OFFICE,
            **overrides,
        )

    def test_missing_office_displays_safe_empty_state_instead_of_404(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No accessible active office location")
        self.assertNotContains(response, "Transfer from office")
        self.assertIsNone(response.context["office"])
        self.assertEqual(list(response.context["stock_items"]), [])

    def test_inactive_office_displays_safe_empty_state(self):
        self.create_office(is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No accessible active office location")

    def test_archived_office_displays_safe_empty_state(self):
        self.create_office(is_active=False, archived_at=timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No accessible active office location")

    def test_deleted_office_displays_safe_empty_state(self):
        self.create_office(is_active=False, deleted_at=timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No accessible active office location")

    def test_active_office_remains_usable(self):
        office = self.create_office()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["office"], office)
        self.assertContains(response, "Transfer from office")
        self.assertContains(response, "No office stock found")

    def test_invalid_explicit_location_still_returns_404(self):
        self.create_office()
        response = self.client.get(self.url, {"location": "UNKNOWN"})
        self.assertEqual(response.status_code, 404)

    def test_out_of_scope_offices_are_not_exposed(self):
        office = self.create_office()
        self.membership.inventory_location_scope_mode = ScopeMode.SELECTED
        self.membership.save(update_fields=("inventory_location_scope_mode",))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["office"])
        self.assertNotContains(response, office.name)
        self.assertEqual(self.client.get(self.url, {"location": office.code}).status_code, 404)

    def test_selected_office_can_be_opened_without_other_office_exposure(self):
        allowed = self.create_office()
        blocked = self.create_office(code="OFFICE-B")
        self.membership.inventory_location_scope_mode = ScopeMode.SELECTED
        self.membership.save(update_fields=("inventory_location_scope_mode",))
        MembershipInventoryLocationScope.objects.create(
            membership=self.membership, inventory_location=allowed
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["office"], allowed)
        self.assertNotContains(response, blocked.code)
        self.assertEqual(self.client.get(self.url, {"location": blocked.code}).status_code, 404)

    def test_login_is_required_before_location_resolution(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
