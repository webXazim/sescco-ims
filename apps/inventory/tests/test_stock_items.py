from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.inventory.models import StockItem, Unit
from apps.inventory.services.matching import find_stock_matches
from apps.projects.models import Project

User = get_user_model()


class StockItemModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper")
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.other_project = Project.objects.create(code="SABIC-02", name="SABIC Extension")
        self.unit = Unit.objects.get(normalized_name="bag")

    def create_item(self, **overrides):
        values = {
            "project": self.project,
            "material_name": "Portland Cement",
            "supplier_name": "Gulf Cement",
            "supplier_phone": "+966 57 368 6575",
            "unit": self.unit,
            "minimum_quantity": Decimal("10"),
            "created_by": self.user,
            "updated_by": self.user,
        }
        values.update(overrides)
        return StockItem.objects.create(**values)

    def test_zero_quantity_display_includes_zero(self):
        item = StockItem.objects.create(
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
        )
        self.assertEqual(item.quantity_display, "0 bag")

    def test_identity_fields_are_normalized(self):
        item = self.create_item(
            material_name="  PORTLAND   Cement ",
            supplier_name=" Gulf   Cement ",
            supplier_phone="00966-57-368-6575",
        )
        self.assertEqual(item.normalized_material_name, "portland cement")
        self.assertEqual(item.normalized_supplier_name, "gulf cement")
        self.assertEqual(item.normalized_supplier_phone, "966573686575")

    def test_same_identity_with_phone_formatting_difference_is_rejected(self):
        self.create_item()
        duplicate = StockItem(
            project=self.project,
            material_name="portland cement",
            supplier_name="GULF CEMENT",
            supplier_phone="00966-57-368-6575",
            unit=self.unit,
        )
        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_same_identity_can_exist_in_another_project(self):
        self.create_item()
        second = self.create_item(project=self.other_project)
        self.assertNotEqual(second.project, self.project)
        self.assertEqual(StockItem.objects.count(), 2)

    def test_completed_project_rejects_new_stock_record(self):
        self.project.status = Project.Status.COMPLETED
        self.project.save()
        with self.assertRaises(ValidationError):
            self.create_item()

    def test_stock_status_is_derived_from_quantity_and_minimum(self):
        item = self.create_item()
        self.assertEqual(item.stock_status, "out")
        item.current_quantity = Decimal("5")
        self.assertEqual(item.stock_status, "low")
        item.current_quantity = Decimal("20")
        self.assertEqual(item.stock_status, "in")

    def test_balance_fields_cannot_be_changed_directly(self):
        item = self.create_item()
        item.current_quantity = Decimal("5")
        with self.assertRaises(ValidationError):
            item.save()

    def test_existing_record_can_keep_completed_project_during_metadata_edit(self):
        item = self.create_item()
        self.project.status = Project.Status.COMPLETED
        self.project.save()
        item.description = "Updated specification"
        item.save()
        self.assertEqual(item.description, "Updated specification")

    def test_existing_record_cannot_move_to_completed_project(self):
        item = self.create_item()
        self.other_project.status = Project.Status.COMPLETED
        self.other_project.save()
        item.project = self.other_project
        with self.assertRaises(ValidationError):
            item.save()

    def test_unit_with_active_stock_record_cannot_be_deactivated(self):
        self.create_item()
        self.unit.is_active = False
        with self.assertRaises(ValidationError):
            self.unit.save()

    def test_existing_record_cannot_switch_to_inactive_unit(self):
        item = self.create_item()
        inactive = Unit.objects.create(name="Pallet", symbol="plt", is_active=False)
        item.unit = inactive
        with self.assertRaises(ValidationError):
            item.save()

    def test_matcher_returns_exact_and_similar_phone_results(self):
        exact = self.create_item()
        exact_result = find_stock_matches(
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="00966 57 368 6575",
        )
        self.assertEqual(exact_result.exact, exact)

        similar_result = find_stock_matches(
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 55 000 0000",
        )
        self.assertIsNone(similar_result.exact)
        self.assertEqual(list(similar_result.similar), [exact])
