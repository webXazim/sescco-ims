import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project
from apps.core.tests.tenant import grant_company_access, primary_company
from apps.accounts.models import MembershipInventoryLocationScope
from apps.accounts.roles import ScopeMode

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
        self.company = primary_company()
        grant_company_access(self.user, company=self.company)
        grant_company_access(self.admin, company=self.company)
        self.project = Project.objects.create(company=self.company, code="SITE-01", name="Finished Site")
        self.other_project = Project.objects.create(company=self.company, code="SITE-02", name="Next Site")
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

    def test_project_page_starts_ordinary_transfer_without_closeout(self):
        response = self.client.get(reverse("projects:detail", args=[self.project.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Transfer stock")
        self.assertContains(
            response,
            f'{reverse("inventory:transfer_create")}?source={self.project.inventory_location.pk}',
        )
        self.assertNotContains(response, "Transfer remaining stock")
        transfer_page = self.client.get(
            reverse("inventory:transfer_create"),
            {"source": self.project.inventory_location.pk},
        )
        self.assertEqual(transfer_page.status_code, 200)
        self.assertContains(transfer_page, "you do not need to move the full balance")
        self.assertContains(transfer_page, "Safety Barrier")
        self.assertNotContains(transfer_page, "Transfer and complete project")

    def test_partial_project_to_office_transfer_keeps_project_active_and_remainder(self):
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                "document_reference": "PARTIAL-100",
                f"item_{self.item.pk}_new": "3",
            },
        )
        self.assertEqual(response.status_code, 302)
        transfer = StockTransfer.objects.get()
        self.assertRedirects(response, reverse("inventory:transfer_detail", args=[transfer.reference]))
        self.item.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("7"))
        self.assertEqual(self.project.status, Project.Status.ACTIVE)
        self.assertIsNone(self.project.end_date)
        destination_item = transfer.lines.get().destination_stock_item
        self.assertEqual(destination_item.location, self.office)
        self.assertEqual(destination_item.current_quantity, Decimal("3"))
        self.assertEqual(StockMovement.objects.filter(transfer_line__transfer=transfer).count(), 2)
        self.assertContains(self.client.get(response.url), "PARTIAL-100")

    def test_full_transfer_does_not_auto_complete_project(self):
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{self.item.pk}_used": "10",
                # Even an old link carrying closeout must not complete projects.
                "closeout": self.project.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACTIVE)
        self.assertIsNone(self.project.end_date)
        self.assertEqual(self.item.current_quantity, Decimal("0"))

    def test_over_allocation_rejected_without_movements(self):
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{self.item.pk}_used": "11",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "only 10", status_code=400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("10"))
        self.assertEqual(StockTransfer.objects.count(), 0)

    def test_office_return_link_preserves_destination_selection(self):
        office = self.client.get(reverse("inventory:office"))
        self.assertContains(
            office,
            f'{reverse("inventory:transfer_create")}?destination={self.office.pk}',
        )
        source_step = self.client.get(
            reverse("inventory:transfer_create"), {"destination": self.office.pk}
        )
        self.assertEqual(source_step.status_code, 200)
        self.assertContains(source_step, f'name="destination" value="{self.office.pk}"')
        form_page = self.client.get(
            reverse("inventory:transfer_create"),
            {"source": self.project.inventory_location.pk, "destination": self.office.pk},
        )
        self.assertEqual(form_page.status_code, 200)
        self.assertEqual(
            form_page.context["form"]["destination_location"].value(),
            self.office.pk,
        )

    def test_view_supports_project_project_and_office_project_partial_transfers(self):
        first = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.other_project.inventory_location.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{self.item.pk}_new": "4",
            },
        )
        self.assertEqual(first.status_code, 302)
        first_destination = StockTransfer.objects.latest("pk").lines.get().destination_stock_item
        self.assertEqual(first_destination.current_quantity, Decimal("4"))
        second = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.other_project.inventory_location.pk,
                "destination_location": self.office.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{first_destination.pk}_new": "2",
            },
        )
        self.assertEqual(second.status_code, 302)
        office_item = StockTransfer.objects.latest("pk").lines.get().destination_stock_item
        third = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.office.pk,
                "destination_location": self.project.inventory_location.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{office_item.pk}_new": "1",
            },
        )
        self.assertEqual(third.status_code, 302)
        self.assertEqual(StockTransfer.objects.count(), 3)
        self.item.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("7"))
        self.assertEqual(self.project.status, Project.Status.ACTIVE)

    def test_held_project_is_not_a_transfer_source_or_destination(self):
        self.other_project.status = Project.Status.ON_HOLD
        self.other_project.save()
        transfer_page = self.client.get(
            reverse("inventory:transfer_create"),
            {"source": self.project.inventory_location.pk},
        )
        self.assertEqual(transfer_page.status_code, 200)
        self.assertNotIn(
            self.other_project.inventory_location.pk,
            transfer_page.context["form"].fields["destination_location"].queryset.values_list("pk", flat=True),
        )
        response = self.client.post(
            reverse("inventory:transfer_create"),
            {
                "source_location": self.project.inventory_location.pk,
                "destination_location": self.other_project.inventory_location.pk,
                "idempotency_key": uuid.uuid4(),
                "transfer_date": timezone.localdate().isoformat(),
                f"item_{self.item.pk}_new": "2",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockTransfer.objects.count(), 0)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("10"))


class StockTransferHistoryFilterTests(StockTransferServiceTests):
    """Transfer history filtering must retain access controls and stable results."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.office_transfer = self._transfer(
            destination_location=self.office,
            allocations=[TransferAllocation(self.item, "new", Decimal("2"))],
            document_reference="OFFICE-RECEIPT",
        ).transfer
        self.project_transfer = self._transfer(
            destination_location=self.other_project.inventory_location,
            allocations=[TransferAllocation(self.item, "used", Decimal("3"))],
            document_reference="SECOND-PROJECT",
            transfer_date=timezone.localdate() - timedelta(days=40),
        ).transfer

    def _search(self, **params):
        response = self.client.get(reverse("inventory:transfer_list"), params)
        self.assertEqual(response.status_code, 200)
        return response

    def test_unfiltered_history_shows_all_scoped_transfers(self):
        response = self._search()
        self.assertEqual(response.context["paginator"].count, 2)
        self.assertContains(response, "OFFICE-RECEIPT")
        self.assertContains(response, "SECOND-PROJECT")
        self.assertContains(response, 'data-live-filter-form')

    def test_status_direction_and_location_filters(self):
        response = self._search(direction="project_office", status="completed")
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "OFFICE-RECEIPT")
        response = self._search(
            source=self.project.inventory_location.pk,
            destination=self.other_project.inventory_location.pk,
        )
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "SECOND-PROJECT")
        response = self._search(source="999999999")
        self.assertEqual(len(response.context["transfers"]), 0)

    def test_reference_material_and_actor_search(self):
        for query in ("SECOND-PROJECT", "Safety Barrier", self.user.username):
            with self.subTest(q=query):
                response = self._search(q=query)
                self.assertGreaterEqual(response.context["paginator"].count, 1)
        response = self._search(q="SECOND-PROJECT")
        self.assertEqual(response.context["paginator"].count, 1)

    def test_preset_custom_date_and_sort(self):
        response = self._search(date_preset="last_7_days")
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "OFFICE-RECEIPT")
        response = self._search(date_from=(timezone.localdate() - timedelta(days=60)).isoformat(),
                                date_to=(timezone.localdate() - timedelta(days=30)).isoformat())
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "SECOND-PROJECT")
        response = self._search(sort="oldest")
        self.assertEqual(response.context["transfers"][0].pk, self.project_transfer.pk)

    def test_invalid_date_range_returns_no_records_without_exception(self):
        response = self._search(date_preset="custom", date_from="2026-10-28", date_to="2026-10-01")
        self.assertEqual(len(response.context["transfers"]), 0)
        self.assertTrue(response.context["transfer_filter_errors"])

    def test_reversed_filter(self):
        reverse_transfer(
            transfer=self.office_transfer,
            user=self.admin,
            idempotency_key=uuid.uuid4(),
            reason="Reversed for filter regression",
        )
        response = self._search(status="reversed")
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "OFFICE-RECEIPT")

    def test_selected_scope_limits_transfer_results_and_filter_options(self):
        membership = self.user.company_memberships.get(company=self.company)
        membership.inventory_location_scope_mode = ScopeMode.SELECTED
        membership.save(update_fields=["inventory_location_scope_mode"])
        for location in (self.project.inventory_location, self.office):
            MembershipInventoryLocationScope.objects.create(
                membership=membership, inventory_location=location
            )
        response = self._search(q="Safety Barrier")
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "OFFICE-RECEIPT")
        self.assertNotContains(response, "SECOND-PROJECT")
        self.assertNotContains(response, self.other_project.inventory_location.code)
        self.assertEqual(self._search(destination=self.other_project.inventory_location.pk).context["paginator"].count, 0)
