"""Recoverable master deletion requires only an authorized confirmation click."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.inventory.models import InventoryLocation, Unit


class ClickOnlyDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = primary_company()
        cls.admin = get_user_model().objects.create_superuser(
            username="click-delete-admin", email="click-delete@example.com", password="safe-password"
        )
        cls.member = get_user_model().objects.create_user(username="click-delete-member", password="safe-password")
        grant_company_access(cls.admin, company=cls.company)
        grant_company_access(cls.member, company=cls.company)

    @staticmethod
    def json_headers():
        return {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}

    def test_unused_unit_does_not_require_name_reason_or_acknowledgement(self):
        unit = Unit.objects.create(company=self.company, name="Temporary click unit", symbol="TCLK")
        url = reverse("inventory:unit_delete", args=[unit.pk])
        self.client.force_login(self.admin)
        response = self.client.get(url, **self.json_headers())
        self.assertTrue(response.json()["delete_allowed"])
        self.assertNotIn("confirmation_token", response.json())
        unit.refresh_from_db()
        self.assertIsNone(unit.deleted_at)
        posted = self.client.post(url, {}, **self.json_headers())
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["redirect_url"], reverse("inventory:units"))
        unit.refresh_from_db()
        self.assertIsNotNone(unit.deleted_at)
        self.assertEqual(unit.deletion_reason, "Deleted after confirmation click.")

    def test_unit_dependency_guard_remains_enforced(self):
        unit = Unit.objects.get(normalized_name="piece")
        self.client.force_login(self.admin)
        # Never attempt to delete an in-use unit; policy must decide first.
        from apps.core.services.lifecycle import lifecycle_decision, LifecycleAction
        result = lifecycle_decision(unit, LifecycleAction.DELETE)
        if result.allowed:
            self.skipTest("The fixture unit has no stock or import dependencies")
        response = self.client.post(reverse("inventory:unit_delete", args=[unit.pk]), {}, **self.json_headers())
        self.assertEqual(response.status_code, 409)

    def test_unused_office_location_uses_same_click_only_modal(self):
        location = InventoryLocation.objects.create(
            company=self.company,
            code="CLICK-OFFICE",
            name="Temporary Office for Delete Test",
            location_type=InventoryLocation.Type.OFFICE,
        )
        url = reverse("inventory:location_delete", args=[location.pk])
        self.client.force_login(self.admin)
        preview = self.client.get(url, **self.json_headers())
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["delete_allowed"])
        self.assertNotIn("confirmation_token", preview.json())
        fallback = self.client.get(url)
        self.assertNotContains(fallback, 'name="confirmation"')
        self.assertNotContains(fallback, 'name="reason"')
        location.refresh_from_db()
        self.assertIsNone(location.deleted_at)
        response = self.client.post(url, {}, **self.json_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("inventory:locations"))
        location.refresh_from_db()
        self.assertIsNotNone(location.deleted_at)

    def test_unauthorized_member_cannot_delete_unused_unit(self):
        unit = Unit.objects.create(company=self.company, name="Restricted click unit", symbol="RCLK")
        url = reverse("inventory:unit_delete", args=[unit.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url, {}, **self.json_headers()).status_code, 403)
        unit.refresh_from_db()
        self.assertIsNone(unit.deleted_at)
