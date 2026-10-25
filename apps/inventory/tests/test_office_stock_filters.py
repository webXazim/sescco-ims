"""Office explorer filters should match Inventory without escaping office scope."""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, MembershipInventoryLocationScope, User
from apps.accounts.roles import AccessRole, ScopeMode
from apps.core.models import Company
from apps.projects.models import Project

from ..models import InventoryLocation, StockItem, Unit
from ..services.stock import add_stock


class OfficeStockFilterTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Office Filter Company", slug="office-filter-company")
        self.user = User.objects.create_user(username="office-filter-user")
        self.membership = CompanyMembership.objects.create(
            company=self.company, user=self.user, role=AccessRole.OWNER
        )
        self.client.force_login(self.user)
        self.office = InventoryLocation.objects.create(
            company=self.company, code="OFF-FILTER-A", name="Main Office",
            location_type=InventoryLocation.Type.OFFICE,
        )
        self.other_office = InventoryLocation.objects.create(
            company=self.company, code="OFF-FILTER-B", name="Other Office",
            location_type=InventoryLocation.Type.OFFICE,
        )
        self.unit = Unit.objects.create(company=self.company, name="Cartons", symbol="ctn")
        self.other_unit = Unit.objects.create(company=self.company, name="Packs", symbol="pack")
        self.today = timezone.localdate()
        self.gloves = self.receive(
            self.office, "Safety Gloves", "Safety Supply", "0511111111",
            self.unit, "12", "5", "8.00", self.today,
        )
        self.helmets = self.receive(
            self.office, "Safety Helmets", "PPE Distributors", "0522222222",
            self.other_unit, "3", "5", "22.00", self.today - timedelta(days=12),
        )
        self.remote_item = self.receive(
            self.other_office, "Remote Wrenches", "Remote Supply", "0533333333",
            self.unit, "15", "2", "15.00", self.today,
        )
        self.project = Project.objects.create(
            company=self.company, code="FILTER-PROJECT", name="Separate Project"
        )
        add_stock(
            user=self.user, idempotency_key=uuid.uuid4(),
            project=self.project, quantity=Decimal("15"), movement_date=self.today,
            material_name="Project Wrenches", supplier_name="Project Supply",
            supplier_phone="0544444444", unit=self.unit,
        )
        self.url = reverse("inventory:office")

    def receive(self, office, material, supplier, phone, unit, quantity, minimum, price, date):
        return add_stock(
            user=self.user, idempotency_key=uuid.uuid4(), location=office,
            quantity=Decimal(quantity), movement_date=date, material_name=material,
            supplier_name=supplier, supplier_phone=phone, unit=unit,
            minimum_quantity=Decimal(minimum), unit_price=Decimal(price),
        ).movement.stock_item

    def results(self, params=None):
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, 200)
        return response, list(response.context["stock_items"])

    def test_office_uses_inventory_compact_live_filter_controls(self):
        response, items = self.results()
        self.assertEqual({i.pk for i in items}, {self.gloves.pk, self.helmets.pk})
        self.assertContains(response, 'data-live-filter-form')
        self.assertContains(response, 'data-live-filter-search')
        self.assertContains(response, 'data-condition-filter')
        self.assertContains(response, 'name="stock_status"')
        self.assertContains(response, 'name="sort"')
        self.assertContains(response, 'name="quantity_min"')
        self.assertContains(response, 'name="price_max"')
        self.assertContains(response, 'data-filter-results')
        self.assertNotContains(response, 'name="project"')
        self.assertNotContains(response, 'name="status"')

    def test_text_search_conditions_and_status_are_server_filtered(self):
        _, items = self.results({"q": "helmets distributors"})
        self.assertEqual([item.pk for item in items], [self.helmets.pk])
        _, items = self.results({"stock_status": "low"})
        self.assertEqual([item.pk for item in items], [self.helmets.pk])
        _, items = self.results({"stock_status": "in"})
        self.assertEqual([item.pk for item in items], [self.gloves.pk])
        _, items = self.results({"condition": [StockItem.Condition.USED]})
        self.assertEqual(items, [])
        _, items = self.results({"condition": [StockItem.Condition.NEW, StockItem.Condition.USED]})
        self.assertEqual({item.pk for item in items}, {self.gloves.pk, self.helmets.pk})

    def test_units_ranges_date_filters_and_sort(self):
        _, items = self.results({"unit": [self.other_unit.pk], "price_min": "20"})
        self.assertEqual([item.pk for item in items], [self.helmets.pk])
        _, items = self.results({"quantity_min": "10", "price_max": "10"})
        self.assertEqual([item.pk for item in items], [self.gloves.pk])
        _, items = self.results({"minimum_min": "5", "minimum_max": "5"})
        self.assertEqual(len(items), 2)
        _, items = self.results({"date_preset": "today"})
        self.assertEqual([item.pk for item in items], [self.gloves.pk])
        _, items = self.results({"sort": "quantity"})
        self.assertEqual([item.pk for item in items], [self.helmets.pk, self.gloves.pk])

    def test_invalid_range_returns_empty_and_displays_error(self):
        response, items = self.results({"quantity_min": "bad"})
        self.assertEqual(items, [])
        self.assertContains(response, "Enter a number")
        response, items = self.results({"quantity_min": "30", "quantity_max": "10"})
        self.assertEqual(items, [])
        self.assertContains(response, "Quantity maximum cannot be below its minimum")

    def test_office_selection_is_location_scoped_and_preserves_filters(self):
        _, items = self.results({"location": self.other_office.code, "q": "Remote"})
        self.assertEqual([item.pk for item in items], [self.remote_item.pk])
        _, items = self.results({"location": self.office.code, "q": "Remote"})
        self.assertEqual(items, [])
        self.assertEqual(self.client.get(self.url, {"location": "FILTER-PROJECT"}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {"location": "not-a-location"}).status_code, 404)

    def test_selected_location_scope_cannot_be_bypassed_with_filters(self):
        self.membership.inventory_location_scope_mode = ScopeMode.SELECTED
        self.membership.save(update_fields=["inventory_location_scope_mode"])
        MembershipInventoryLocationScope.objects.create(
            membership=self.membership, inventory_location=self.office
        )
        _, items = self.results({"q": "wrenches"})
        self.assertEqual(items, [])
        response, _ = self.results()
        self.assertNotContains(response, self.other_office.code)
        self.assertEqual(
            self.client.get(self.url, {"location": self.other_office.code}).status_code, 404
        )
