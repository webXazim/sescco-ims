"""Stock deletion dialog protects historical inventory and company access."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.inventory.models import StockItem, Unit
from apps.projects.models import Project


class StockDeleteDialogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = primary_company()
        cls.admin = get_user_model().objects.create_superuser(
            username="stock-delete-dialog-admin", email="sd@example.com", password="safe-password"
        )
        cls.member = get_user_model().objects.create_user(
            username="stock-delete-dialog-member", password="safe-password"
        )
        grant_company_access(cls.admin, company=cls.company)
        grant_company_access(cls.member, company=cls.company)
        cls.project = Project.objects.create(company=cls.company, code="STK-MODAL", name="Stock Dialog")
        cls.unit = Unit.objects.get(normalized_name="piece")
        cls.item = StockItem.objects.create(
            project=cls.project,
            material_name="Unused sample",
            supplier_name="Vendor",
            supplier_phone="0500000001",
            unit=cls.unit,
        )

    def request_kwargs(self):
        return {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}

    def test_actions_use_dialog_from_stock_list_and_detail(self):
        self.client.force_login(self.admin)
        url = reverse("inventory:delete", args=[self.item.reference])
        for page in (reverse("inventory:list"), reverse("inventory:detail", args=[self.item.reference])):
            response = self.client.get(page)
            self.assertContains(response, 'data-inventory-delete href="' + url + '"')
            self.assertContains(response, 'data-inventory-delete-dialog')

    def test_modal_confirmation_and_server_validation(self):
        self.client.force_login(self.admin)
        url = reverse("inventory:delete", args=[self.item.reference])
        details = self.client.get(url, **self.request_kwargs())
        self.assertTrue(details.json()["delete_allowed"])
        token = details.json()["confirmation_token"]
        self.assertEqual(token, str(self.item.reference)[:8].upper())

        mismatch = self.client.post(url, {
            "reason": "Duplicate", "acknowledge": "yes", "confirmation": "incorrect"
        }, **self.request_kwargs())
        self.assertEqual(mismatch.status_code, 409)
        self.assertIn(token, mismatch.json()["error"])
        self.item.refresh_from_db()
        self.assertIsNone(self.item.deleted_at)

        response = self.client.post(url, {
            "reason": "Duplicate", "acknowledge": "yes", "confirmation": token
        }, **self.request_kwargs())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("inventory:list"))
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.deleted_at)

    def test_in_use_stock_is_blocked_inside_modal(self):
        protected = StockItem.objects.create(
            project=self.project,
            material_name="Existing material",
            supplier_name="Supplier 2",
            supplier_phone="0500000002",
            unit=self.unit,
            current_quantity=Decimal("12"),
        )
        self.client.force_login(self.admin)
        url = reverse("inventory:delete", args=[protected.reference])
        details = self.client.get(url, **self.request_kwargs())
        self.assertFalse(details.json()["delete_allowed"])
        self.assertTrue(details.json()["blockers"])
        response = self.client.post(url, {
            "confirmation": str(protected.reference)[:8].upper(),
            "reason": "Mistake", "acknowledge": "yes",
        }, **self.request_kwargs())
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["delete_allowed"])
        protected.refresh_from_db()
        self.assertIsNone(protected.deleted_at)

    def test_permission_is_enforced_for_get_and_post(self):
        self.client.force_login(self.member)
        url = reverse("inventory:delete", args=[self.item.reference])
        self.assertEqual(self.client.get(url, **self.request_kwargs()).status_code, 403)
        self.assertEqual(self.client.post(url, {}, **self.request_kwargs()).status_code, 403)
