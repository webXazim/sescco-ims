import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.inventory.models import StockItem, StockMovement, Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project


User = get_user_model()


class AdministrationExperienceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-password",
        )
        self.keeper = User.objects.create_user(
            username="keeper",
            email="keeper@example.com",
            password="safe-password",
        )
        self.project = Project.objects.create(code="ADMIN-01", name="Admin Project")
        self.unit = Unit.objects.get(normalized_name="bag")
        result = add_stock(
            user=self.admin,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("12"),
            movement_date=date.today(),
            project=self.project,
            material_name="Admin Cement",
            supplier_name="Admin Supplier",
            supplier_phone="0500000000",
            unit=self.unit,
            minimum_quantity=Decimal("3"),
        )
        self.stock_item = result.movement.stock_item
        self.movement = result.movement
        self.client.force_login(self.admin)

    def test_admin_index_links_back_to_workspace(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System administration")
        self.assertContains(response, "Daily operations")
        self.assertContains(response, "Configuration and audit")
        self.assertEqual(response.context["site_url"], "/app/")

    def test_admin_changelists_and_user_creation_form_load(self):
        for url_name in (
            "admin:accounts_user_changelist",
            "admin:projects_project_changelist",
            "admin:inventory_unit_changelist",
            "admin:inventory_stockitem_changelist",
            "admin:inventory_stockmovement_changelist",
            "admin:explorer_savedview_changelist",
            "admin:data_exchange_importjob_changelist",
            "admin:data_exchange_importrow_changelist",
            "admin:data_exchange_exportaudit_changelist",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create account")

    def test_stock_admin_uses_safe_workspace_controls(self):
        add_response = self.client.get(reverse("admin:inventory_stockitem_add"))
        self.assertEqual(add_response.status_code, 403)

        response = self.client.get(
            reverse("admin:inventory_stockitem_change", args=[self.stock_item.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workspace actions")
        self.assertContains(response, "Adjust safely")
        self.assertContains(response, "Movement history")

    def test_movement_admin_is_read_only_and_exposes_safe_reversal(self):
        response = self.client.get(
            reverse("admin:inventory_stockmovement_change", args=[self.movement.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open movement details")
        self.assertContains(response, "Reverse safely")
        self.assertNotContains(response, 'name="_save"')

    def test_bulk_deactivation_protects_current_admin(self):
        response = self.client.post(
            reverse("admin:accounts_user_changelist"),
            {
                "action": "deactivate_accounts",
                "_selected_action": [self.admin.pk, self.keeper.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.keeper.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertFalse(self.keeper.is_active)
