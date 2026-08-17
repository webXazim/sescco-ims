import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project

from ..models import InventoryLocation, StockItem, StockMovement, StockTransfer
from ..services.stock import InsufficientStockError, add_stock
from ..services.transfers import (
    TransferAllocation,
    TransferAlreadyReversedError,
    reverse_transfer,
    transfer_stock,
)


class StockTransferServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="keeper")
        self.admin = user_model.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.project = Project.objects.create(code="SITE-01", name="Finished Site")
        self.other_project = Project.objects.create(code="SITE-02", name="Next Site")
        self.office = InventoryLocation.objects.get(location_type=InventoryLocation.Type.OFFICE)
        self.unit = self._unit()
        self.item = add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Safety Barrier",
            supplier_name="Site Supply",
            supplier_phone="+966 50 100 2000",
            unit=self.unit,
            unit_price=Decimal("100"),
        ).movement.stock_item

    @staticmethod
    def _unit():
        from ..models import Unit

        return Unit.objects.get(normalized_name="piece")

    def _transfer(self, **overrides):
        values = {
            "user": self.user,
            "idempotency_key": uuid.uuid4(),
            "source_location": self.project.inventory_location,
            "destination_location": self.office,
            "transfer_date": timezone.localdate(),
            "allocations": [
                TransferAllocation(self.item, "new", Decimal("2")),
                TransferAllocation(self.item, "used", Decimal("5")),
                TransferAllocation(self.item, "no_value", Decimal("2")),
                TransferAllocation(self.item, "lost", Decimal("1")),
            ],
            "document_reference": "TR-100",
        }
        values.update(overrides)
        return transfer_stock(**values)

    def test_condition_split_reconciles_source_destination_and_loss(self):
        result = self._transfer()
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("0"))
        balances = dict(
            StockItem.objects.filter(location=self.office).values_list(
                "condition", "current_quantity"
            )
        )
        self.assertEqual(
            balances,
            {"new": Decimal("2"), "used": Decimal("5"), "no_value": Decimal("2")},
        )
        no_value = StockItem.objects.get(location=self.office, condition="no_value")
        self.assertEqual(no_value.latest_unit_price, Decimal("0"))
        self.assertEqual(result.transfer.lines.count(), 4)
        self.assertEqual(
            StockMovement.objects.filter(transfer_line__transfer=result.transfer).count(), 7
        )
        self.assertEqual(
            StockMovement.objects.filter(
                transfer_line__transfer=result.transfer,
                movement_type=StockMovement.Type.LOSS,
            ).count(),
            1,
        )

    def test_duplicate_submission_does_not_move_stock_twice(self):
        key = uuid.uuid4()
        first = self._transfer(idempotency_key=key)
        second = self._transfer(idempotency_key=key)
        self.assertTrue(second.duplicate_submission)
        self.assertEqual(first.transfer.pk, second.transfer.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("0"))

    def test_over_allocation_rolls_back_entire_transfer(self):
        with self.assertRaises(InsufficientStockError):
            self._transfer(
                allocations=[TransferAllocation(self.item, "used", Decimal("11"))]
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("10"))
        self.assertEqual(StockTransfer.objects.count(), 0)

    def test_project_to_project_and_office_to_project_are_supported(self):
        first = self._transfer(
            destination_location=self.other_project.inventory_location,
            allocations=[TransferAllocation(self.item, "used", Decimal("4"))],
        )
        destination = first.transfer.lines.get().destination_stock_item
        second = transfer_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            source_location=self.other_project.inventory_location,
            destination_location=self.office,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(destination, "used", Decimal("4"))],
        )
        office_item = second.transfer.lines.get().destination_stock_item
        third = transfer_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            source_location=self.office,
            destination_location=self.project.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(office_item, "used", Decimal("2"))],
        )
        self.assertEqual(third.transfer.destination_location, self.project.inventory_location)

    def test_admin_reverses_entire_transfer(self):
        transfer = self._transfer().transfer
        key = uuid.uuid4()
        first = reverse_transfer(
            transfer=transfer,
            user=self.admin,
            idempotency_key=key,
            reason="Incorrect destination",
        )
        transfer.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.Status.REVERSED)
        self.assertEqual(self.item.current_quantity, Decimal("10"))
        self.assertFalse(
            StockItem.objects.filter(location=self.office, current_quantity__gt=0).exists()
        )
        duplicate = reverse_transfer(
            transfer=transfer,
            user=self.admin,
            idempotency_key=key,
            reason="Incorrect destination",
        )
        self.assertEqual(duplicate.transfer.pk, first.transfer.pk)
        self.assertTrue(duplicate.duplicate_submission)
        with self.assertRaises(TransferAlreadyReversedError):
            reverse_transfer(
                transfer=transfer,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                reason="Again",
            )


class StockTransferViewTests(StockTransferServiceTests):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_transfer_routes_render_for_inventory_user(self):
        self.assertEqual(self.client.get(reverse("inventory:transfer_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inventory:office")).status_code, 200)
        response = self.client.get(
            reverse("inventory:transfer_create"), {"source": self.project.inventory_location.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Safety Barrier")
        self.assertContains(response, "No value")

    def test_closeout_transfer_completes_project_and_shows_receipt(self):
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "closeout": self.project.code,
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                "document_reference": "CLOSE-100",
                f"item_{self.item.pk}_new": "2",
                f"item_{self.item.pk}_used": "5",
                f"item_{self.item.pk}_no_value": "2",
                f"item_{self.item.pk}_lost": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        transfer = StockTransfer.objects.get()
        self.assertRedirects(
            response,
            reverse("inventory:transfer_detail", args=[transfer.reference]),
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.COMPLETED)
        receipt = self.client.get(response.url)
        self.assertContains(receipt, "CLOSE-100")
        self.assertContains(receipt, "Lost")
        office = self.client.get(reverse("inventory:office"))
        self.assertContains(office, "Safety Barrier", count=3)

    def test_closeout_rejects_unallocated_balance(self):
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "closeout": self.project.code,
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{self.item.pk}_used": "9",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "requires all", status_code=400)
        self.project.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACTIVE)
        self.assertEqual(self.item.current_quantity, Decimal("10"))
