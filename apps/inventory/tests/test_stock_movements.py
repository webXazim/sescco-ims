import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.inventory.models import StockItem, StockMovement, Unit
from apps.inventory.services.stock import (
    InactiveStockError,
    InsufficientStockError,
    InventoryOperationError,
    MovementAlreadyReversedError,
    add_opening_stock,
    add_stock,
    adjust_stock,
    reverse_movement,
    set_stock_item_status,
    use_stock,
)
from apps.projects.models import Project

User = get_user_model()


class StockMovementServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper")
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-password",
        )
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.other_project = Project.objects.create(code="NEOM-02", name="NEOM Works")
        self.bag = Unit.objects.get(normalized_name="bag")
        self.piece = Unit.objects.get(normalized_name="piece")
        self.today = timezone.localdate()

    def add(self, **overrides):
        values = {
            "user": self.user,
            "idempotency_key": uuid.uuid4(),
            "quantity": Decimal("50"),
            "movement_date": self.today,
            "project": self.project,
            "material_name": "Portland Cement",
            "description": "50 KG bag",
            "supplier_name": "Gulf Cement",
            "supplier_phone": "+966 57 368 6575",
            "supplier_location": "Dammam",
            "unit": self.bag,
            "minimum_quantity": Decimal("10"),
            "unit_price": Decimal("24.50"),
            "invoice_reference": "INV-100",
            "notes": "Initial delivery",
        }
        values.update(overrides)
        return add_stock(**values)

    def test_add_stock_creates_record_and_movement(self):
        result = self.add()
        item = result.movement.stock_item
        item.refresh_from_db()
        self.assertTrue(result.stock_item_created)
        self.assertEqual(item.current_quantity, Decimal("50"))
        self.assertEqual(item.latest_unit_price, Decimal("24.50"))
        self.assertEqual(item.latest_addition_date, self.today)
        self.assertEqual(result.movement.previous_balance, Decimal("0"))
        self.assertEqual(result.movement.new_balance, Decimal("50"))
        self.assertEqual(result.movement.created_by, self.user)

    def test_exact_normalized_identity_updates_existing_record(self):
        first = self.add()
        second = self.add(
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("20"),
            material_name=" portland   CEMENT ",
            supplier_name="GULF CEMENT",
            supplier_phone="00966-57-368-6575",
            unit_price=Decimal("26"),
            invoice_reference="INV-101",
        )
        first.movement.stock_item.refresh_from_db()
        self.assertFalse(second.stock_item_created)
        self.assertEqual(StockItem.objects.count(), 1)
        self.assertEqual(first.movement.stock_item.current_quantity, Decimal("70"))
        self.assertEqual(first.movement.stock_item.latest_unit_price, Decimal("26"))
        self.assertEqual(StockMovement.objects.count(), 2)


    def test_addition_without_price_preserves_latest_known_price(self):
        first = self.add(unit_price=Decimal("24.50")).movement
        self.add(
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            unit_price=None,
            invoice_reference="DELIVERY-NO-PRICE",
        )
        first.stock_item.refresh_from_db()
        self.assertEqual(first.stock_item.latest_unit_price, Decimal("24.50"))
        self.assertEqual(first.stock_item.latest_addition_date, self.today)

    def test_same_identity_in_another_project_creates_separate_stock(self):
        self.add()
        self.add(project=self.other_project, idempotency_key=uuid.uuid4())
        self.assertEqual(StockItem.objects.count(), 2)

    def test_exact_match_with_different_unit_is_blocked(self):
        self.add()
        with self.assertRaises(InventoryOperationError):
            self.add(idempotency_key=uuid.uuid4(), unit=self.piece)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_similar_phone_requires_confirmation(self):
        self.add()
        with self.assertRaises(InventoryOperationError):
            self.add(
                idempotency_key=uuid.uuid4(),
                supplier_phone="+966 55 000 0000",
            )
        confirmed = self.add(
            idempotency_key=uuid.uuid4(),
            supplier_phone="+966 55 000 0000",
            confirm_similar=True,
        )
        self.assertTrue(confirmed.stock_item_created)
        self.assertEqual(StockItem.objects.count(), 2)

    def test_idempotency_key_returns_existing_movement(self):
        token = uuid.uuid4()
        first = self.add(idempotency_key=token)
        second = self.add(idempotency_key=token)
        self.assertTrue(second.duplicate_submission)
        self.assertEqual(first.movement.pk, second.movement.pk)
        self.assertEqual(StockMovement.objects.count(), 1)
        first.movement.stock_item.refresh_from_db()
        self.assertEqual(first.movement.stock_item.current_quantity, Decimal("50"))

    def test_usage_decreases_balance_and_blocks_negative_stock(self):
        item = self.add().movement.stock_item
        result = use_stock(
            stock_item=item,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("15"),
            movement_date=self.today,
            purpose="Ground-floor block work",
            recipient="Masonry team",
        )
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("35"))
        self.assertEqual(result.movement.movement_type, StockMovement.Type.USAGE)
        with self.assertRaises(InsufficientStockError):
            use_stock(
                stock_item=item,
                user=self.user,
                idempotency_key=uuid.uuid4(),
                quantity=Decimal("36"),
                movement_date=self.today,
                purpose="Invalid request",
            )
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("35"))

    def test_adjustments_require_reason_and_preserve_history(self):
        item = self.add().movement.stock_item
        with self.assertRaises(InventoryOperationError):
            adjust_stock(
                stock_item=item,
                user=self.user,
                idempotency_key=uuid.uuid4(),
                direction="increase",
                quantity=Decimal("5"),
                movement_date=self.today,
                reason="",
            )
        result = adjust_stock(
            stock_item=item,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            direction="decrease",
            quantity=Decimal("4"),
            movement_date=self.today,
            reason="Damaged bags",
        )
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("46"))
        self.assertEqual(result.movement.reason, "Damaged bags")

    def test_reversal_creates_opposite_movement_and_keeps_original(self):
        original = self.add().movement
        item = original.stock_item
        item.material_name = "Corrected current material"
        item.supplier_phone = "+966 50 999 9999"
        item.save()
        reversal = reverse_movement(
            movement=original,
            user=self.admin,
            idempotency_key=uuid.uuid4(),
            movement_date=self.today,
            reason="Duplicate supplier invoice",
        ).movement
        original.stock_item.refresh_from_db()
        self.assertEqual(original.stock_item.current_quantity, Decimal("0"))
        self.assertEqual(reversal.movement_type, StockMovement.Type.REVERSAL)
        self.assertEqual(reversal.reversal_of, original)
        self.assertEqual(reversal.material_name_display, "Portland Cement")
        self.assertEqual(reversal.supplier_phone_display, "+966 57 368 6575")
        self.assertEqual(StockMovement.objects.count(), 2)
        original.refresh_from_db()
        self.assertTrue(original.is_reversed)
        with self.assertRaises(MovementAlreadyReversedError):
            reverse_movement(
                movement=original,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                movement_date=self.today,
                reason="Second reversal",
            )

    def test_inbound_reversal_is_blocked_when_it_would_make_stock_negative(self):
        original = self.add().movement
        use_stock(
            stock_item=original.stock_item,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=self.today,
            purpose="Used on site",
        )
        with self.assertRaises(InsufficientStockError):
            reverse_movement(
                movement=original,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                movement_date=self.today,
                reason="Cannot safely reverse",
            )

    def test_reversing_latest_addition_recalculates_latest_price(self):
        first = self.add(unit_price=Decimal("20"), invoice_reference="INV-1").movement
        second = self.add(
            idempotency_key=uuid.uuid4(),
            unit_price=Decimal("25"),
            quantity=Decimal("10"),
            invoice_reference="INV-2",
        ).movement
        reverse_movement(
            movement=second,
            user=self.admin,
            idempotency_key=uuid.uuid4(),
            movement_date=self.today,
            reason="Incorrect delivery",
        )
        first.stock_item.refresh_from_db()
        self.assertEqual(first.stock_item.latest_unit_price, Decimal("20"))

    def test_opening_stock_only_allowed_before_other_movements(self):
        item = StockItem.objects.create(
            project=self.project,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 111 1111",
            unit=self.piece,
        )
        add_opening_stock(
            stock_item=item,
            user=self.admin,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("100"),
            movement_date=self.today,
        )
        with self.assertRaises(InventoryOperationError):
            add_opening_stock(
                stock_item=item,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                quantity=Decimal("10"),
                movement_date=self.today,
            )

    def test_opening_stock_requires_inventory_admin(self):
        item = StockItem.objects.create(
            project=self.project,
            material_name="Copper Cable",
            supplier_name="Cable Supplier",
            supplier_phone="+966 50 222 2222",
            unit=self.piece,
        )
        with self.assertRaises(InventoryOperationError):
            add_opening_stock(
                stock_item=item,
                user=self.user,
                idempotency_key=uuid.uuid4(),
                quantity=Decimal("10"),
                movement_date=self.today,
            )

    def test_reversal_requires_inventory_admin(self):
        movement = self.add().movement
        with self.assertRaises(InventoryOperationError):
            reverse_movement(
                movement=movement,
                user=self.user,
                idempotency_key=uuid.uuid4(),
                movement_date=self.today,
                reason="Unauthorized correction",
            )
        movement.stock_item.refresh_from_db()
        self.assertEqual(movement.stock_item.current_quantity, Decimal("50"))

    def test_reversal_requires_active_project_and_stock_record(self):
        addition = self.add(quantity=Decimal("10")).movement
        usage = use_stock(
            stock_item=addition.stock_item,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=self.today,
            purpose="Use all stock",
        ).movement
        self.project.status = Project.Status.COMPLETED
        self.project.save()

        with self.assertRaises(InactiveStockError):
            reverse_movement(
                movement=usage,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                movement_date=self.today,
                reason="Correction requires project reactivation",
            )

    def test_reversal_date_cannot_precede_original(self):
        original = self.add(movement_date=self.today).movement
        with self.assertRaises(InventoryOperationError):
            reverse_movement(
                movement=original,
                user=self.admin,
                idempotency_key=uuid.uuid4(),
                movement_date=self.today - timedelta(days=1),
                reason="Invalid backdated correction",
            )

    def test_future_dates_and_inactive_projects_are_blocked(self):
        with self.assertRaises(InventoryOperationError):
            self.add(movement_date=self.today + timedelta(days=1))
        self.project.status = Project.Status.COMPLETED
        self.project.save()
        with self.assertRaises(InactiveStockError):
            self.add(idempotency_key=uuid.uuid4())

    def test_movements_are_immutable(self):
        movement = self.add().movement
        movement.notes = "Attempted edit"
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()

    def test_movement_identity_snapshot_survives_stock_metadata_edit(self):
        movement = self.add().movement
        item = movement.stock_item
        item.material_name = "Updated Cement Name"
        item.supplier_name = "Updated Supplier"
        item.supplier_phone = "+966 50 999 9999"
        item.save()
        movement.refresh_from_db()
        self.assertEqual(movement.material_name_display, "Portland Cement")
        self.assertEqual(movement.supplier_name_display, "Gulf Cement")
        self.assertEqual(movement.supplier_phone_display, "+966 57 368 6575")
        self.assertEqual(
            movement.supplier_phone_normalized_snapshot, "966573686575"
        )
        self.assertEqual(movement.project_code_display, "ARAMCO-01")
        self.assertEqual(movement.unit_symbol_display, self.bag.symbol)

    def test_project_and_unit_are_locked_after_first_movement(self):
        item = self.add().movement.stock_item
        item.project = self.other_project
        with self.assertRaises(ValidationError):
            item.save()
        item.refresh_from_db()
        item.unit = self.piece
        with self.assertRaises(ValidationError):
            item.save()

    def test_stock_record_lifecycle_requires_zero_balance(self):
        item = self.add().movement.stock_item
        with self.assertRaises(InventoryOperationError):
            set_stock_item_status(
                stock_item=item, user=self.user, status=StockItem.Status.ARCHIVED
            )
        use_stock(
            stock_item=item,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("50"),
            movement_date=self.today,
            purpose="Use remaining stock",
        )
        archived = set_stock_item_status(
            stock_item=item, user=self.user, status=StockItem.Status.ARCHIVED
        )
        self.assertEqual(archived.status, StockItem.Status.ARCHIVED)
        active = set_stock_item_status(
            stock_item=item, user=self.user, status=StockItem.Status.ACTIVE
        )
        self.assertEqual(active.status, StockItem.Status.ACTIVE)
