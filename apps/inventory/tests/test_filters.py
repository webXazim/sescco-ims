import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.explorer.models import TablePreference
from apps.inventory.models import StockMovement, Unit
from apps.inventory.services.stock import add_stock, use_stock
from apps.projects.models import Project

User = get_user_model()


class AdvancedExplorerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.aramco = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.neom = Project.objects.create(code="NEOM-04", name="NEOM Site Works")
        self.unit = Unit.objects.get(normalized_name="bag")
        self.cement = add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("50"),
            movement_date=self.today,
            project=self.aramco,
            material_name="Portland Cement",
            description="50 KG bag",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            supplier_location="Dammam",
            unit=self.unit,
            minimum_quantity=Decimal("10"),
            unit_price=Decimal("24.50"),
            invoice_reference="INV-100",
        ).movement.stock_item
        add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            movement_date=self.today - timedelta(days=40),
            project=self.neom,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 000 0000",
            unit=self.unit,
            minimum_quantity=Decimal("10"),
            unit_price=Decimal("80"),
        )

    def test_inventory_combines_all_filters(self):
        response = self.client.get(
            reverse("inventory:list"),
            {
                "project": self.aramco.code,
                "material": "cement",
                "supplier_phone": "966573686575",
                "quantity_min": "40",
                "price_max": "30",
            },
        )
        self.assertContains(response, "Portland Cement")
        self.assertNotContains(response, "Steel Bar")

    def test_search_terms_use_and_semantics_across_columns(self):
        response = self.client.get(reverse("inventory:list"), {"q": "ARAMCO Gulf cement"})
        self.assertContains(response, "Portland Cement")
        response = self.client.get(reverse("inventory:list"), {"q": "ARAMCO Metal"})
        self.assertNotContains(response, "Portland Cement")

    def test_inventory_search_covers_record_context_and_reference(self):
        self.aramco.client_name = "Saudi Aramco"
        self.aramco.location = "Eastern Province"
        self.aramco.notes = "Coastal expansion package"
        self.aramco.save()
        self.user.email = "keeper@inventory.example"
        self.user.save(update_fields=["email"])

        searchable_values = (
            "Saudi",
            "Eastern",
            "Coastal",
            "50 KG",
            "Dammam",
            "bag",
            "keeper@inventory.example",
            str(self.cement.reference),
        )
        for query in searchable_values:
            with self.subTest(query=query):
                response = self.client.get(reverse("inventory:list"), {"q": query})
                self.assertContains(response, "Portland Cement")

    def test_inventory_uses_compact_live_search_filter_ui(self):
        response = self.client.get(
            reverse("inventory:list"),
            {"q": "cement", "quantity_min": "1"},
        )
        self.assertContains(response, "data-live-filter-search")
        self.assertContains(response, "data-live-filter-form")
        self.assertContains(response, "filter-popover is-hidden")
        self.assertContains(response, "data-column-settings")
        self.assertContains(response, "Save columns")
        self.assertContains(response, "All projects")
        self.assertContains(response, "Sort by project")
        self.assertContains(response, 'name="quantity_min"')
        self.assertNotContains(response, 'name="material"')
        self.assertNotContains(response, 'name="project_status"')
        self.assertNotContains(response, 'name="supplier_phone"')

    def test_custom_dates_render_beside_quick_filters(self):
        response = self.client.get(
            reverse("inventory:list"),
            {
                "date_preset": "custom",
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
            },
        )
        self.assertContains(response, 'class="date-range-popover"')
        self.assertContains(response, "Latest stock addition date")
        self.assertContains(response, "data-close-date-range")
        self.assertContains(response, "filter-popover is-hidden")

    def test_activity_uses_compact_live_search_with_closed_filters(self):
        response = self.client.get(reverse("core:activity"), {"q": "cement"})
        self.assertContains(response, "data-live-filter-search")
        self.assertContains(response, "data-live-filter-form")
        self.assertContains(response, "data-filter-results")
        self.assertContains(response, "filter-popover is-hidden")
        self.assertContains(response, "data-column-settings")
        self.assertContains(response, "data-quick-date-range")

    def test_management_unit_and_supplier_searches_are_live(self):
        units = self.client.get(reverse("inventory:units"), {"q": "bag"})
        self.assertContains(units, "data-live-filter-search")
        self.assertContains(units, '<td class="cell-main">Bag</td>')
        self.assertNotContains(units, '<td class="cell-main">Box</td>')

        suppliers = self.client.get(reverse("inventory:suppliers"), {"q": "573686575"})
        self.assertContains(suppliers, "data-live-filter-search")
        self.assertContains(suppliers, "Gulf Cement")
        self.assertNotContains(suppliers, "Metal Supplier")

    def test_date_presets_filter_activity(self):
        response = self.client.get(reverse("core:activity"), {"date_preset": "today"})
        self.assertContains(response, "Portland Cement")
        self.assertNotContains(response, "Steel Bar")

    def test_custom_date_range_includes_boundaries(self):
        date = self.today - timedelta(days=40)
        response = self.client.get(
            reverse("core:activity"),
            {"date_preset": "custom", "date_from": date.isoformat(), "date_to": date.isoformat()},
        )
        self.assertContains(response, "Steel Bar")
        self.assertNotContains(response, "Portland Cement")

    def test_movement_filters_reference_user_quantity_and_type(self):
        use_stock(
            stock_item=self.cement,
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("2"),
            movement_date=self.today,
            purpose="Block work",
            recipient="Team A",
            invoice_reference="USE-44",
        )
        response = self.client.get(
            reverse("core:activity"),
            {
                "movement_type": StockMovement.Type.USAGE,
                "reference": "USE-44",
                "recipient": "Team A",
                "quantity_min": "2",
                "quantity_max": "2",
                "created_by": self.user.pk,
            },
        )
        self.assertContains(response, "Block work")
        self.assertNotContains(response, "INV-100")

    def test_visible_columns_are_url_driven(self):
        response = self.client.get(
            reverse("inventory:list"), {"columns": ["project", "material", "quantity"]}
        )
        self.assertContains(response, "Project")
        self.assertContains(response, "Material")
        self.assertNotContains(response, "<th>Supplier location</th>")

    def test_table_columns_are_saved_per_user_and_view(self):
        endpoint = reverse("inventory:column_preferences")
        response = self.client.post(
            endpoint,
            {
                "view_type": "inventory",
                "columns": ["project", "material", "quantity"],
                "next": reverse("inventory:list"),
            },
        )
        self.assertRedirects(response, reverse("inventory:list"))
        preference = TablePreference.objects.get(owner=self.user, view_type="inventory")
        self.assertEqual(preference.columns, ["project", "material", "quantity"])

        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.context["visible_columns"], ("project", "material", "quantity"))
        self.assertNotContains(response, "<th>Supplier</th>")

        activity = self.client.get(reverse("core:activity"))
        self.assertIn("date", activity.context["visible_columns"])
        self.assertFalse(
            TablePreference.objects.filter(owner=self.user, view_type="activity").exists()
        )

        response = self.client.post(
            endpoint,
            {"view_type": "inventory", "reset": "1", "next": reverse("inventory:list")},
        )
        self.assertRedirects(response, reverse("inventory:list"))
        self.assertFalse(
            TablePreference.objects.filter(
                owner=self.user, view_type="inventory"
            ).exists()
        )

    def test_stock_detail_history_has_date_and_action_filters(self):
        response = self.client.get(
            reverse("inventory:detail", args=[self.cement.reference]),
            {"movement_type": StockMovement.Type.ADDITION, "date_preset": "today"},
        )
        self.assertContains(response, "Stock added")
