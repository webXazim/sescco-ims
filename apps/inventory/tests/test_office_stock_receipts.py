"""Office receipts and linked project/office transfer regression coverage."""

import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import AccessRole, ScopeMode
from apps.core.tests.tenant import grant_company_access, primary_company
from apps.projects.models import Project

from ..models import InventoryLocation, StockItem, StockMovement, StockTransfer, Supplier, Unit
from ..services.stock import InventoryOperationError, add_stock
from ..services.transfers import TransferAllocation, transfer_stock


class OfficeStockReceiptTests(TestCase):
    def setUp(self):
        self.company = primary_company()
        self.user = User.objects.create_user(username="office-receipts")
        self.membership = grant_company_access(
            self.user, company=self.company, role=AccessRole.OWNER
        )
        self.client.force_login(self.user)
        self.office = InventoryLocation.objects.for_company(self.company).filter(
            location_type=InventoryLocation.Type.OFFICE,
            deleted_at__isnull=True,
        ).order_by("pk").first()
        if self.office is None:
            self.office = InventoryLocation.objects.create(
                company=self.company,
                code="OFFICE-REGRESSION",
                name="Main Office",
                location_type=InventoryLocation.Type.OFFICE,
            )
        self.unit = Unit.objects.create(
            company=self.company, name="Office regression unit", symbol="oru"
        )
        self.supplier = Supplier.objects.create(
            company=self.company, name="Office Test Supply", phone="0501234567"
        )
        self.project_a = Project.objects.create(
            company=self.company, code="OFFTEST-001", name="Office Test Project A"
        )
        self.project_b = Project.objects.create(
            company=self.company, code="OFFTEST-002", name="Office Test Project B"
        )

    def office_payload(self, key=None):
        return {
            "office_code": self.office.code,
            "idempotency_key": str(key or uuid.uuid4()),
            "movement_date": timezone.localdate().isoformat(),
            "material_name": "Safety Gloves",
            "description": "Site PPE",
            "supplier": str(self.supplier.pk),
            "unit": str(self.unit.pk),
            "minimum_quantity": "2",
            "quantity": "20",
            "unit_price": "12.50",
            "invoice_reference": "OFF-INV-001",
            "notes": "Initial office receipt",
        }

    def create_office_stock(self, *, key=None, quantity="20"):
        return add_stock(
            user=self.user,
            idempotency_key=key or uuid.uuid4(),
            location=self.office,
            quantity=Decimal(quantity),
            movement_date=timezone.localdate(),
            material_name="Safety Gloves",
            description="Site PPE",
            supplier_name=self.supplier.name,
            supplier_phone=self.supplier.phone,
            unit=self.unit,
            unit_price=Decimal("12.50"),
        )

    def test_office_page_has_add_stock_action_and_form_needs_no_project(self):
        response = self.client.get(reverse("inventory:office"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add office stock")
        response = self.client.get(reverse("inventory:office_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Office and material")
        self.assertContains(response, "Main Office")
        self.assertFalse(response.context["form"].fields["project"].required)

    def test_office_receipt_posts_without_project_and_creates_history(self):
        response = self.client.post(reverse("inventory:office_add"), self.office_payload())
        self.assertEqual(response.status_code, 302)
        item = StockItem.objects.for_company(self.company).get(
            location=self.office, normalized_material_name="safety gloves"
        )
        self.assertIsNone(item.project_id)
        self.assertEqual(item.current_quantity, Decimal("20"))
        self.assertEqual(item.latest_unit_price, Decimal("12.50"))
        movement = item.movements.get()
        self.assertEqual(movement.movement_type, StockMovement.Type.ADDITION)
        self.assertEqual(movement.quantity, Decimal("20"))
        self.assertEqual(movement.invoice_reference, "OFF-INV-001")

    def test_same_office_identity_merges_and_duplicate_key_is_idempotent(self):
        key = uuid.uuid4()
        self.create_office_stock(key=key)
        duplicate = self.create_office_stock(key=key)
        self.assertTrue(duplicate.duplicate_submission)
        again = self.create_office_stock(quantity="5")
        self.assertFalse(again.stock_item_created)
        item = again.movement.stock_item
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("25"))
        self.assertEqual(item.movements.count(), 2)
        self.assertEqual(StockItem.objects.filter(location=self.office, material_name="Safety Gloves").count(), 1)

    def test_live_office_match_is_limited_to_authorized_office(self):
        item = self.create_office_stock().movement.stock_item
        response = self.client.get(reverse("inventory:matches"), {
            "office": self.office.pk,
            "material_name": item.material_name,
            "supplier_name": self.supplier.name,
            "supplier_phone": self.supplier.phone,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exact"]["reference"], str(item.reference))
        self.assertEqual(response.json()["exact"]["project_code"], self.office.code)

    def test_direct_office_stock_transfers_to_project_and_back_then_other_project(self):
        office_item = self.create_office_stock().movement.stock_item
        outgoing = transfer_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            source_location=self.office,
            destination_location=self.project_a.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(office_item, "new", Decimal("12"))],
        )
        office_item.refresh_from_db()
        self.assertEqual(office_item.current_quantity, Decimal("8"))
        project_item = outgoing.transfer.lines.get().destination_stock_item
        self.assertEqual(project_item.project_id, self.project_a.pk)
        returned = transfer_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            source_location=self.project_a.inventory_location,
            destination_location=self.office,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(project_item, "used", Decimal("4"))],
        )
        used_office_item = returned.transfer.lines.get().destination_stock_item
        self.assertEqual(used_office_item.project_id, None)
        self.assertEqual(used_office_item.condition, StockItem.Condition.USED)
        transfer_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            source_location=self.project_a.inventory_location,
            destination_location=self.project_b.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(project_item, "new", Decimal("3"))],
        )
        project_item.refresh_from_db()
        self.assertEqual(project_item.current_quantity, Decimal("5"))
        self.assertEqual(StockTransfer.objects.for_company(self.company).count(), 3)

    def test_selected_location_scope_cannot_receive_office_stock(self):
        self.membership.inventory_location_scope_mode = ScopeMode.SELECTED
        self.membership.save(update_fields=("inventory_location_scope_mode",))
        self.assertEqual(self.client.get(reverse("inventory:office_add")).status_code, 404)
        response = self.client.get(reverse("inventory:office"))
        self.assertContains(response, "Reactivate Main Office")
        with self.assertRaises(InventoryOperationError):
            self.create_office_stock()
        restored = self.client.post(reverse("inventory:location_status", args=[self.office.pk]), {
            "action": "restore", "return_to": "office",
        })
        self.assertRedirects(restored, reverse("inventory:office"))
        self.office.refresh_from_db()
        self.assertTrue(self.office.is_active)
        self.assertIsNone(self.office.archived_at)
        self.assertEqual(self.client.get(reverse("inventory:office_add")).status_code, 200)
        self.assertEqual(StockMovement.objects.for_company(self.company).count(), 0)

    def test_archived_office_does_not_accept_new_receipts(self):
        self.office.is_active = False
        self.office.archived_at = timezone.now()
        self.office.save()
        self.assertEqual(self.client.get(reverse("inventory:office_add")).status_code, 404)
        with self.assertRaises(InventoryOperationError):
            self.create_office_stock()
