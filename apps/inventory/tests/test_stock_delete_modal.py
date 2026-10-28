"""Stock delete dialog hides operational records without erasing their history."""

from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

from django.core.management import call_command
from django.utils import timezone
from django.core.exceptions import ValidationError

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.inventory.models import StockItem, Unit, StockMovement
from apps.inventory.services.stock import add_stock, use_stock, InactiveStockError
from apps.inventory.selectors import stock_items, stock_movements
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
        self.assertNotIn("confirmation_token", details.json())
        self.item.refresh_from_db()
        self.assertIsNone(self.item.deleted_at)

        response = self.client.post(url, {}, **self.request_kwargs())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("inventory:list"))
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.deleted_at)

    def test_quantity_and_movement_history_can_be_soft_deleted_and_restored(self):
        result = add_stock(
            user=self.admin,
            idempotency_key=uuid4(),
            quantity=Decimal("12"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Existing material",
            supplier_name="Supplier 2",
            supplier_phone="0500000002",
            unit=self.unit,
        )
        protected = result.movement.stock_item
        movement_id = result.movement.pk
        self.client.force_login(self.admin)
        url = reverse("inventory:delete", args=[protected.reference])
        details = self.client.get(url, **self.request_kwargs())
        self.assertEqual(details.status_code, 200)
        self.assertTrue(details.json()["delete_allowed"])
        self.assertEqual(details.json()["blockers"], [])
        self.assertTrue(any("remaining quantity" in effect for effect in details.json()["effects"]))
        self.assertTrue(any("audit history" in effect for effect in details.json()["effects"]))

        response = self.client.post(url, {
            "confirmation": protected.material_name,
            
        }, **self.request_kwargs())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], reverse("inventory:list"))
        protected.refresh_from_db()
        self.assertIsNotNone(protected.deleted_at)
        self.assertEqual(protected.current_quantity, Decimal("12"))
        self.assertEqual(protected.deletion_reason, "Deleted after confirmation click.")
        self.assertFalse(stock_items(self.company).filter(pk=protected.pk).exists())
        self.assertFalse(stock_movements(self.company).filter(pk=movement_id).exists())
        self.assertEqual(StockMovement.objects.get(pk=movement_id).stock_item_id, protected.pk)
        self.assertEqual(StockMovement.objects.get(pk=movement_id).new_balance, Decimal("12"))

        # The deleted inventory identity cannot continue receiving operations.
        with self.assertRaises(InactiveStockError):
            use_stock(
                stock_item=protected,
                user=self.admin,
                idempotency_key=uuid4(),
                quantity=Decimal("1"),
                movement_date=timezone.localdate(),
                purpose="Should be blocked",
            )

        response = self.client.post(reverse("inventory:trash_restore", args=["stock", protected.reference]))
        self.assertEqual(response.status_code, 302)
        protected.refresh_from_db()
        self.assertIsNone(protected.deleted_at)
        self.assertEqual(protected.current_quantity, Decimal("12"))
        self.assertTrue(stock_items(self.company).filter(pk=protected.pk).exists())
        self.assertTrue(stock_movements(self.company).filter(pk=movement_id).exists())

    def test_expired_deleted_stock_with_history_keeps_immutable_tombstone(self):
        result = add_stock(
            user=self.admin,
            idempotency_key=uuid4(),
            quantity=Decimal("1"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Historical material",
            supplier_name="Supplier 3",
            supplier_phone="0500000003",
            unit=self.unit,
        )
        item = result.movement.stock_item
        self.client.force_login(self.admin)
        self.client.post(reverse("inventory:delete", args=[item.reference]), {
            "confirmation": item.material_name,
            
        })
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)
        item.purge_after = timezone.now() - timedelta(days=1)
        item.save(update_fields=["purge_after"])
        call_command("purge_trash")
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)
        self.assertIsNone(item.purge_after)
        self.assertEqual(item.current_quantity, Decimal("1"))
        self.assertTrue(StockMovement.objects.filter(pk=result.movement.pk).exists())

    def test_service_allows_delete_without_typed_name_or_reason(self):
        from apps.inventory.services.lifecycle import trash_unused_stock_item
        from apps.accounts.models import CompanyMembership
        membership = CompanyMembership.objects.get(user=self.admin, company=self.company)
        trash_unused_stock_item(
            actor_membership=membership, stock_item_id=self.item.pk,
            confirmation="", reason="",
        )
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.deleted_at)

    def test_permission_is_enforced_for_get_and_post(self):
        self.client.force_login(self.member)
        url = reverse("inventory:delete", args=[self.item.reference])
        self.assertEqual(self.client.get(url, **self.request_kwargs()).status_code, 403)
        self.assertEqual(self.client.post(url, {}, **self.request_kwargs()).status_code, 403)
