import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import (
    CompanyMembership,
    MembershipInventoryLocationScope,
    MembershipProjectScope,
    User,
)
from apps.accounts.roles import AccessRole, ScopeMode
from apps.core.models import Company
from apps.inventory.access import (
    restrict_inventory_location_queryset,
    restrict_inventory_projects,
    restrict_inventory_stock,
)
from apps.inventory.models import InventoryLocation, StockItem, StockTransferLine, Unit
from apps.inventory.services.stock import InventoryOperationError, add_stock, adjust_stock, use_stock
from apps.inventory.services.transfers import TransferAllocation, transfer_stock
from apps.projects.models import Project


class StorekeeperScopedAuthorityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Storekeeper Scope Co", slug="storekeeper-scope")
        self.owner_user = User.objects.create_user(username="scope-owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner_user,
            role=AccessRole.OWNER,
        )
        self.allowed_project = Project.objects.create(
            company=self.company, code="STORE-A", name="Allowed Store Project"
        )
        self.transfer_project = Project.objects.create(
            company=self.company, code="STORE-B", name="Allowed Transfer Project"
        )
        self.blocked_project = Project.objects.create(
            company=self.company, code="STORE-X", name="Blocked Project"
        )
        self.office = InventoryLocation.objects.create(
            company=self.company,
            code="OFFICE-A",
            name="Allowed Office",
            location_type=InventoryLocation.Type.OFFICE,
        )
        self.blocked_office = InventoryLocation.objects.create(
            company=self.company,
            code="OFFICE-X",
            name="Blocked Office",
            location_type=InventoryLocation.Type.OFFICE,
        )
        self.unit = Unit.objects.create(company=self.company, name="Piece", symbol="pc")
        today = timezone.localdate()
        self.allowed_item = add_stock(
            user=self.owner_user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=today,
            project=self.allowed_project,
            material_name="Allowed Material",
            supplier_name="Allowed Supplier",
            supplier_phone="+966500000001",
            unit=self.unit,
        ).movement.stock_item
        self.blocked_item = add_stock(
            user=self.owner_user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=today,
            project=self.blocked_project,
            material_name="Blocked Material",
            supplier_name="Blocked Supplier",
            supplier_phone="+966500000002",
            unit=self.unit,
        ).movement.stock_item

        self.storekeeper_user = User.objects.create_user(
            username="scoped-storekeeper", password="test-password"
        )
        self.storekeeper = CompanyMembership.objects.create(
            company=self.company,
            user=self.storekeeper_user,
            role=AccessRole.STOREKEEPER,
            project_scope_mode=ScopeMode.SELECTED,
            inventory_location_scope_mode=ScopeMode.SELECTED,
        )
        for project in (self.allowed_project, self.transfer_project):
            MembershipProjectScope.objects.create(membership=self.storekeeper, project=project)
            MembershipInventoryLocationScope.objects.create(
                membership=self.storekeeper,
                inventory_location=project.inventory_location,
            )
        MembershipInventoryLocationScope.objects.create(
            membership=self.storekeeper, inventory_location=self.office
        )
        self.client.force_login(self.storekeeper_user)

    def test_storekeeper_profile_is_exact_and_excludes_high_risk_permissions(self):
        expected = {
            AccessPermission.INVENTORY_DASHBOARD_VIEW.value,
            AccessPermission.INVENTORY_STOCK_VIEW.value,
            AccessPermission.INVENTORY_STOCK_RECEIVE.value,
            AccessPermission.INVENTORY_STOCK_ISSUE.value,
            AccessPermission.INVENTORY_STOCK_TRANSFER.value,
            AccessPermission.INVENTORY_MOVEMENTS_VIEW.value,
            AccessPermission.INVENTORY_PROJECTS_VIEW.value,
            AccessPermission.INVENTORY_SUPPLIERS_VIEW.value,
            AccessPermission.INVENTORY_LOCATIONS_VIEW.value,
            AccessPermission.INVENTORY_EXPORT_EXECUTE.value,
            AccessPermission.SHARED_SEARCH_USE.value,
        }
        actual = set(
            self.storekeeper.access_profile.permission_grants.values_list("permission", flat=True)
        )
        self.assertEqual(actual, expected)
        for forbidden in (
            AccessPermission.INVENTORY_STOCK_ADJUST,
            AccessPermission.INVENTORY_MOVEMENTS_REVERSE,
            AccessPermission.INVENTORY_PROJECTS_MANAGE,
            AccessPermission.INVENTORY_SUPPLIERS_MANAGE,
            AccessPermission.INVENTORY_LOCATIONS_MANAGE,
            AccessPermission.INVENTORY_IMPORT_EXECUTE,
            AccessPermission.SHARED_ARCHIVE_VIEW,
            AccessPermission.SHARED_TRASH_VIEW,
        ):
            self.assertNotIn(forbidden.value, actual)

    def test_project_location_and_stock_queries_apply_both_scopes(self):
        projects = list(
            restrict_inventory_projects(
                Project.objects.for_company(self.company).order_by("code"), self.storekeeper
            )
        )
        self.assertEqual(
            [project.code for project in projects],
            [self.allowed_project.code, self.transfer_project.code],
        )
        locations = list(
            restrict_inventory_location_queryset(
                InventoryLocation.objects.for_company(self.company).order_by("code"), self.storekeeper
            )
        )
        self.assertEqual(
            {location.code for location in locations},
            {self.allowed_project.inventory_location.code, self.transfer_project.inventory_location.code, self.office.code},
        )
        stock = list(
            restrict_inventory_stock(
                StockItem.objects.for_company(self.company).order_by("material_name"), self.storekeeper
            )
        )
        self.assertEqual([item.pk for item in stock], [self.allowed_item.pk])

    def test_direct_stock_page_cannot_open_out_of_scope_record(self):
        allowed = self.client.get(
            reverse("inventory:detail", kwargs={"reference": self.allowed_item.reference})
        )
        blocked = self.client.get(
            reverse("inventory:detail", kwargs={"reference": self.blocked_item.reference})
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 404)

    def test_storekeeper_can_issue_in_scope_but_not_out_of_scope(self):
        use_stock(
            stock_item=self.allowed_item,
            user=self.storekeeper_user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("1"),
            movement_date=timezone.localdate(),
            purpose="Scoped use",
        )
        with self.assertRaises(InventoryOperationError):
            use_stock(
                stock_item=self.blocked_item,
                user=self.storekeeper_user,
                idempotency_key=uuid.uuid4(),
                quantity=Decimal("1"),
                movement_date=timezone.localdate(),
                purpose="Blocked use",
            )

    def test_storekeeper_transfer_requires_both_locations_in_scope(self):
        result = transfer_stock(
            user=self.storekeeper_user,
            idempotency_key=uuid.uuid4(),
            source_location=self.allowed_project.inventory_location,
            destination_location=self.transfer_project.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[
                TransferAllocation(
                    source_stock_item=self.allowed_item,
                    outcome=StockTransferLine.Outcome.NEW,
                    quantity=Decimal("1"),
                )
            ],
        )
        self.assertFalse(result.duplicate_submission)
        with self.assertRaises(InventoryOperationError):
            transfer_stock(
                user=self.storekeeper_user,
                idempotency_key=uuid.uuid4(),
                source_location=self.allowed_project.inventory_location,
                destination_location=self.blocked_project.inventory_location,
                transfer_date=timezone.localdate(),
                allocations=[
                    TransferAllocation(
                        source_stock_item=self.allowed_item,
                        outcome=StockTransferLine.Outcome.NEW,
                        quantity=Decimal("1"),
                    )
                ],
            )

    def test_storekeeper_cannot_adjust_stock_or_open_imports(self):
        with self.assertRaises(InventoryOperationError):
            adjust_stock(
                stock_item=self.allowed_item,
                user=self.storekeeper_user,
                idempotency_key=uuid.uuid4(),
                direction="increase",
                quantity=Decimal("1"),
                movement_date=timezone.localdate(),
                reason="Forbidden correction",
            )
        response = self.client.get(reverse("data_exchange:import_list"))
        self.assertEqual(response.status_code, 403)

    def test_storekeeper_cannot_manage_projects_suppliers_or_units(self):
        self.assertEqual(self.client.get(reverse("projects:create")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("inventory:supplier_edit", kwargs={"pk": 1})).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("inventory:units")).status_code, 403)

    def test_dashboard_and_exports_do_not_leak_blocked_project(self):
        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, self.allowed_project.code)
        self.assertNotContains(dashboard, self.blocked_project.code)

        export = self.client.get(reverse("data_exchange:inventory_export", args=["csv"]))
        self.assertEqual(export.status_code, 200)
        body = b"".join(export.streaming_content).decode("utf-8") if getattr(export, "streaming", False) else export.content.decode("utf-8")
        self.assertIn("Allowed Material", body)
        self.assertNotIn("Blocked Material", body)
