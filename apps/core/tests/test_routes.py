import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import StockItem, Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project

User = get_user_model()


class WorkspaceRouteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.client.force_login(self.user)
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.unit = Unit.objects.get(normalized_name="bag")
        self.item = StockItem.objects.create(
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
        )
        self.movement = add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
        ).movement

    def test_all_upgrade_five_routes_render(self):
        routes = [
            "core:dashboard",
            "core:activity",
            "core:add_stock",
            "core:remove_stock",
            "explorer:saved_views",
            "projects:list",
            "projects:create",
            "inventory:list",
            "inventory:picker",
            "inventory:low_stock",
            "inventory:units",
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_legacy_stock_create_route_redirects_to_add_stock(self):
        response = self.client.get(reverse("inventory:create"))
        self.assertRedirects(
            response,
            reverse("core:add_stock"),
            fetch_redirect_response=False,
        )

    def test_detail_routes_render(self):
        self.assertEqual(
            self.client.get(reverse("inventory:detail", args=[self.item.reference])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("inventory:movement_detail", args=[self.movement.reference])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("projects:detail", args=[self.project.code])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("inventory:adjust", args=[self.item.reference])).status_code,
            200,
        )

    def test_health_endpoint(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["database"], "ready")
