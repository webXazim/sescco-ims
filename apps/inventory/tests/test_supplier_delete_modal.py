"""Supplier deletion uses the shared modal and preserves copied inventory history."""

from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.inventory.models import StockItem, StockMovement, Supplier, Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project


class SupplierDeleteDialogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = primary_company()
        cls.admin = get_user_model().objects.create_superuser(
            username="supplier-delete-dialog-admin", password="safe-password", email="supd@example.com"
        )
        cls.member = get_user_model().objects.create_user(
            username="supplier-delete-dialog-member", password="safe-password"
        )
        grant_company_access(cls.admin, company=cls.company)
        grant_company_access(cls.member, company=cls.company)
        cls.supplier = Supplier.objects.create(
            company=cls.company, name="Lulu Khazan Establishment", phone="0569813342", location="Dammam"
        )
        cls.project = Project.objects.create(company=cls.company, code="SUP-MODAL", name="Supplier Delete Test")
        cls.unit = Unit.objects.get(normalized_name="piece")

    @staticmethod
    def ajax_headers():
        return {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}

    def test_delete_is_available_from_list_and_edit_without_confirmation_page(self):
        self.client.force_login(self.admin)
        url = reverse("inventory:supplier_delete", args=[self.supplier.pk])
        for page in (reverse("inventory:suppliers"), reverse("inventory:supplier_edit", args=[self.supplier.pk])):
            response = self.client.get(page)
            self.assertContains(response, 'data-inventory-delete href="' + url + '"')
            self.assertContains(response, 'data-inventory-delete-dialog')

    def test_supplier_with_stock_history_can_be_soft_deleted_and_restored(self):
        result = add_stock(
            user=self.admin,
            idempotency_key=uuid4(),
            quantity=Decimal("7"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Steel bars",
            supplier_name=self.supplier.name,
            supplier_phone=self.supplier.phone,
            unit=self.unit,
        )
        item_pk = result.movement.stock_item.pk
        movement_pk = result.movement.pk
        self.client.force_login(self.admin)
        url = reverse("inventory:supplier_delete", args=[self.supplier.pk])
        modal = self.client.get(url, **self.ajax_headers())
        self.assertEqual(modal.status_code, 200)
        self.assertTrue(modal.json()["delete_allowed"])
        self.assertEqual(modal.json()["blockers"], [])
        self.assertNotIn("confirmation_token", modal.json())
        self.assertTrue(any("will not be changed" in effect for effect in modal.json()["effects"]))

        # GET must remain read-only; no name field is required for POST.
        self.supplier.refresh_from_db()
        self.assertIsNone(self.supplier.deleted_at)

        deleted = self.client.post(url, {}, **self.ajax_headers())
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["redirect_url"], reverse("inventory:suppliers"))
        self.supplier.refresh_from_db()
        self.assertIsNotNone(self.supplier.deleted_at)
        self.assertEqual(self.supplier.deletion_reason, "Deleted after confirmation click.")
        self.assertEqual((self.supplier.purge_after - self.supplier.deleted_at).days, 30)
        self.assertFalse(Supplier.objects.for_company(self.company).filter(pk=self.supplier.pk, deleted_at__isnull=True).exists())
        self.assertTrue(StockItem.objects.filter(pk=item_pk).exists())
        movement = StockMovement.objects.get(pk=movement_pk)
        self.assertEqual(movement.stock_item_id, item_pk)
        item = StockItem.objects.get(pk=item_pk)
        self.assertEqual(item.supplier_name, self.supplier.name)
        self.assertEqual(item.supplier_phone, self.supplier.phone)
        self.assertEqual(item.current_quantity, Decimal("7"))

        trash = self.client.get(reverse("inventory:trash"))
        self.assertContains(trash, self.supplier.name)
        restored = self.client.post(reverse("inventory:trash_restore", args=["supplier", self.supplier.pk]))
        self.assertRedirects(restored, reverse("inventory:trash"))
        self.supplier.refresh_from_db()
        self.assertIsNone(self.supplier.deleted_at)
        self.assertTrue(Supplier.objects.for_company(self.company).filter(pk=self.supplier.pk, deleted_at__isnull=True).exists())
        self.assertEqual(StockMovement.objects.get(pk=movement_pk).stock_item_id, item_pk)

    def test_member_cannot_request_or_submit_supplier_deletion(self):
        self.client.force_login(self.member)
        url = reverse("inventory:supplier_delete", args=[self.supplier.pk])
        self.assertEqual(self.client.get(url, **self.ajax_headers()).status_code, 403)
        self.assertEqual(self.client.post(url, {}, **self.ajax_headers()).status_code, 403)

    def test_locations_link_hidden_from_sidebar_only(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("inventory:suppliers"))
        self.assertNotContains(response, 'href="' + reverse("inventory:locations") + '"')
        self.assertContains(response, 'href="' + reverse("inventory:units") + '"')
        self.assertContains(response, 'href="' + reverse("inventory:suppliers") + '"')
        self.assertEqual(self.client.get(reverse("inventory:locations")).status_code, 200)
