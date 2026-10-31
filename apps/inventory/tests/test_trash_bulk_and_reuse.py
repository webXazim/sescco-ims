"""Trash removal and active-only identity regression coverage."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.core.trash import cascade_to_trash, move_to_trash
from apps.inventory.models import StockItem, StockMovement, Supplier, Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project


class TrashAndMasterReuseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = primary_company()
        cls.admin = get_user_model().objects.create_superuser(
            username="trash-bulk-admin", email="trashbulk@example.com", password="valid-password"
        )
        cls.regular = get_user_model().objects.create_user(
            username="trash-bulk-member", password="valid-password"
        )
        grant_company_access(cls.admin, company=cls.company)
        grant_company_access(cls.regular, company=cls.company)

    def setUp(self):
        self.client.force_login(self.admin)

    def supplier(self, *, name="Duplicate Supplier", phone="0501234567"):
        return Supplier.objects.create(company=self.company, name=name, phone=phone)

    def test_trashed_supplier_can_be_recreated_then_old_one_cannot_be_restored(self):
        previous = self.supplier()
        move_to_trash(previous, user=self.admin, reason="Duplicate")
        create = self.client.post(reverse("inventory:suppliers"), {
            "name": previous.name, "phone": previous.phone, "location": "Dammam", "notes": "",
        })
        self.assertRedirects(create, reverse("inventory:suppliers"))
        newer = Supplier.objects.for_company(self.company).get(
            name=previous.name, deleted_at__isnull=True
        )
        self.assertNotEqual(newer.pk, previous.pk)
        response = self.client.post(reverse("inventory:trash_restore", args=["supplier", previous.pk]))
        self.assertRedirects(response, reverse("inventory:trash"))
        previous.refresh_from_db()
        self.assertIsNotNone(previous.deleted_at)
        self.assertEqual(Supplier.objects.for_company(self.company).filter(
            normalized_name=previous.normalized_name, deleted_at__isnull=True
        ).count(), 1)

    def test_trash_selected_deletes_only_checked_supplier(self):
        first = self.supplier(name="First supplier")
        second = self.supplier(name="Second supplier")
        for item in (first, second):
            move_to_trash(item, user=self.admin, reason="Duplicate")
        screen = self.client.get(reverse("inventory:trash"))
        self.assertContains(screen, 'name="selected"')
        self.assertContains(screen, "Empty Trash")
        response = self.client.post(reverse("inventory:trash_delete"), {
            "action": "selected", "selected": [f"supplier:{first.pk}"],
        })
        self.assertRedirects(response, reverse("inventory:trash"))
        self.assertFalse(Supplier.objects.filter(pk=first.pk).exists())
        second.refresh_from_db()
        self.assertIsNotNone(second.purge_after)
        self.assertContains(self.client.get(reverse("inventory:trash")), second.name)

    def test_empty_trash_removes_all_company_records_even_with_filtered_view(self):
        for name in ("First supplier", "Second supplier"):
            move_to_trash(self.supplier(name=name), user=self.admin, reason="Duplicate")
        self.client.get(reverse("inventory:trash"), {"q": "first"})
        result = self.client.post(reverse("inventory:trash_delete"), {"action": "empty"})
        self.assertRedirects(result, reverse("inventory:trash"))
        self.assertFalse(Supplier.objects.for_company(self.company).filter(
            deleted_at__isnull=False, purge_after__gt=timezone.now()
        ).exists())

    def test_history_bearing_stock_is_hidden_but_stock_and_movement_remain(self):
        project = Project.objects.create(company=self.company, code="TRASH-STOCK", name="Trash stock")
        unit = Unit.objects.for_company(self.company).get(normalized_name="piece")
        result = add_stock(
            user=self.admin, idempotency_key=uuid4(), quantity=Decimal("3"),
            movement_date=timezone.localdate(), project=project,
            material_name="Copper plate", supplier_name="Steel Company",
            supplier_phone="0559988776", unit=unit,
        )
        item = result.movement.stock_item
        movement_pk = result.movement.pk
        move_to_trash(item, user=self.admin, reason="Old record")
        response = self.client.post(reverse("inventory:trash_delete"), {
            "action": "selected", "selected": [f"stock:{item.reference}"],
        })
        self.assertRedirects(response, reverse("inventory:trash"))
        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)
        self.assertIsNone(item.purge_after)
        self.assertEqual(item.current_quantity, Decimal("3"))
        self.assertTrue(StockMovement.objects.filter(pk=movement_pk, stock_item=item).exists())
        self.assertNotContains(self.client.get(reverse("inventory:trash")), "Copper plate")

    def test_empty_trash_also_dismisses_project_owned_cascade_children(self):
        project = Project.objects.create(company=self.company, code="TRASH-PARENT", name="Deleted project")
        unit = Unit.objects.for_company(self.company).get(normalized_name="piece")
        result = add_stock(
            user=self.admin, idempotency_key=uuid4(), quantity=Decimal("2"),
            movement_date=timezone.localdate(), project=project,
            material_name="Project history item", supplier_name="Source vendor",
            supplier_phone="0501230000", unit=unit,
        )
        stock = result.movement.stock_item
        location = stock.location
        move_to_trash(project, user=self.admin, reason="Project no longer used")
        cascade_to_trash(root=project, children=[stock, location], user=self.admin, reason="Project no longer used")
        self.assertContains(self.client.get(reverse("inventory:trash")), "TRASH-PARENT")
        response = self.client.post(reverse("inventory:trash_delete"), {"action": "empty"})
        self.assertRedirects(response, reverse("inventory:trash"))
        self.assertEqual(self.client.get(reverse("inventory:trash")).context["paginator"].count, 0)
        stock.refresh_from_db()
        location.refresh_from_db()
        project.refresh_from_db()
        self.assertIsNone(stock.purge_after)
        self.assertIsNone(location.purge_after)
        self.assertIsNone(project.purge_after)
        self.assertTrue(StockMovement.objects.filter(pk=result.movement.pk).exists())

    def test_selected_delete_rejects_invalid_scope_and_anonymous(self):
        record = self.supplier()
        move_to_trash(record, user=self.admin, reason="Mistake")
        url = reverse("inventory:trash_delete")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"action": "selected", "selected": ["supplier:99999999"]}).status_code, 400)
        record.refresh_from_db()
        self.assertIsNotNone(record.purge_after)
        self.client.force_login(self.regular)
        self.assertEqual(self.client.post(url, {"action": "empty"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, {"action": "empty"}).status_code, 302)

    def test_trashed_unit_can_be_recreated_but_restoring_conflicting_unit_fails(self):
        unit = Unit.objects.create(company=self.company, name="Old Special Unit", symbol="osu")
        move_to_trash(unit, user=self.admin, reason="Mistake")
        created = self.client.post(reverse("inventory:units"), {"name": "Old Special Unit", "symbol": "osu"})
        self.assertRedirects(created, reverse("inventory:units"))
        self.client.post(reverse("inventory:trash_restore", args=["unit", unit.pk]))
        unit.refresh_from_db()
        self.assertIsNotNone(unit.deleted_at)
