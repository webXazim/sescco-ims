import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.explorer.models import SavedView
from apps.inventory.models import Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project

User = get_user_model()


class SavedViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.other = User.objects.create_user(username="other", password="safe-password")
        self.client.force_login(self.user)
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.unit = Unit.objects.get(normalized_name="bag")
        add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("50"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
        )

    def test_create_saved_inventory_view_whitelists_query(self):
        response = self.client.post(
            reverse("explorer:saved_view_create"),
            {
                "name": "Aramco cement",
                "view_type": SavedView.ViewType.INVENTORY,
                "source_query": "project=ARAMCO-01&q=cement&page=9&unexpected=secret",
            },
        )
        saved = SavedView.objects.get(owner=self.user)
        self.assertEqual(saved.query_params, {"q": "cement", "project": "ARAMCO-01"})
        self.assertRedirects(
            response,
            f"{reverse('inventory:list')}?q=cement&project=ARAMCO-01",
            fetch_redirect_response=False,
        )

    def test_open_saved_view_replays_filters(self):
        saved = SavedView.objects.create(
            owner=self.user,
            name="Today additions",
            view_type=SavedView.ViewType.ACTIVITY,
            query_params={"date_preset": "today", "movement_type": ["addition"]},
        )
        response = self.client.get(reverse("explorer:saved_view_open", args=[saved.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("date_preset=today", response.url)
        self.assertIn("movement_type=addition", response.url)

    def test_saved_views_are_private_to_owner(self):
        saved = SavedView.objects.create(
            owner=self.other,
            name="Private",
            view_type=SavedView.ViewType.INVENTORY,
            query_params={},
        )
        self.assertEqual(
            self.client.get(reverse("explorer:saved_view_open", args=[saved.pk])).status_code,
            404,
        )

    def test_rename_and_delete(self):
        saved = SavedView.objects.create(
            owner=self.user,
            name="Old name",
            view_type=SavedView.ViewType.LOW_STOCK,
            query_params={"stock_status": "low"},
        )
        self.client.post(
            reverse("explorer:saved_view_rename", args=[saved.pk]),
            {"name": "New name"},
        )
        saved.refresh_from_db()
        self.assertEqual(saved.name, "New name")
        self.client.post(reverse("explorer:saved_view_delete", args=[saved.pk]))
        self.assertFalse(SavedView.objects.filter(pk=saved.pk).exists())

    def test_saved_view_management_search_is_live(self):
        SavedView.objects.create(
            owner=self.user,
            name="Daily additions",
            view_type=SavedView.ViewType.ACTIVITY,
            query_params={"date_preset": "today"},
        )
        SavedView.objects.create(
            owner=self.user,
            name="Low cement",
            view_type=SavedView.ViewType.LOW_STOCK,
            query_params={"q": "cement"},
        )
        response = self.client.get(reverse("explorer:saved_views"), {"q": "daily"})
        self.assertContains(response, "data-live-filter-search")
        self.assertContains(response, "Daily additions")
        self.assertNotContains(response, "Low cement")
