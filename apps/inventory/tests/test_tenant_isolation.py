import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.core.tests.tenant import grant_company_access, primary_company
from apps.data_exchange.models import ExportAudit
from apps.explorer.models import SavedView
from apps.projects.models import Project

from ..models import InventoryLocation, StockItem, StockTransfer, StockTransferLine, Unit
from ..services.stock import InventoryOperationError, add_stock

User = get_user_model()


class InventoryTenantIsolationTests(TestCase):
    def setUp(self):
        self.company_a = primary_company()
        self.company_b = Company.objects.create(
            name="Second Company",
            legal_name="Second Company",
            slug="second-company",
        )
        self.user_a = User.objects.create_user(username="keeper-a", password="safe-password")
        self.user_b = User.objects.create_user(username="owner-b", password="safe-password")
        self.admin_a = User.objects.create_superuser(
            username="admin-a", email="admin-a@example.com", password="safe-password"
        )
        grant_company_access(self.user_a, company=self.company_a, role=AccessRole.STOREKEEPER)
        grant_company_access(self.admin_a, company=self.company_a, role=AccessRole.OWNER)
        grant_company_access(self.user_b, company=self.company_b, role=AccessRole.OWNER)

        self.project_a = Project.objects.create(
            company=self.company_a, code="SHARED-01", name="Company A Project"
        )
        self.project_b = Project.objects.create(
            company=self.company_b, code="SHARED-01", name="Company B Project"
        )
        self.unit_a = Unit.objects.for_company(self.company_a).get(normalized_name="piece")
        self.unit_b = Unit.objects.create(company=self.company_b, name="Piece", symbol="pc")

        self.item_a = add_stock(
            user=self.user_a,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            movement_date=timezone.localdate(),
            project=self.project_a,
            material_name="Company A Material",
            supplier_name="Supplier A",
            supplier_phone="0500000001",
            unit=self.unit_a,
        ).movement.stock_item
        self.item_b = add_stock(
            user=self.user_b,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("7"),
            movement_date=timezone.localdate(),
            project=self.project_b,
            material_name="Company B Material",
            supplier_name="Supplier B",
            supplier_phone="0500000002",
            unit=self.unit_b,
        ).movement.stock_item

        self.client.force_login(self.user_a)

    def test_same_project_code_is_allowed_in_different_companies(self):
        self.assertEqual(Project.objects.filter(code="SHARED-01").count(), 2)

    def test_inventory_and_project_lists_do_not_leak_other_company(self):
        projects = self.client.get(reverse("projects:list"))
        self.assertContains(projects, "Company A Project")
        self.assertNotContains(projects, "Company B Project")

        inventory = self.client.get(reverse("inventory:list"))
        self.assertContains(inventory, "Company A Material")
        self.assertNotContains(inventory, "Company B Material")

    def test_other_company_detail_routes_return_not_found(self):
        project_response = self.client.get(
            reverse("projects:detail", kwargs={"code": self.project_b.code})
        )
        # Project codes are company-scoped; the same code resolves to Company A's project.
        self.assertEqual(project_response.status_code, 200)
        self.assertEqual(project_response.context["project"].pk, self.project_a.pk)

        stock_response = self.client.get(
            reverse("inventory:detail", kwargs={"reference": self.item_b.reference})
        )
        self.assertEqual(stock_response.status_code, 404)

    def test_service_layer_rejects_actor_without_target_company_access(self):
        with self.assertRaises(InventoryOperationError):
            add_stock(
                user=self.user_a,
                idempotency_key=uuid.uuid4(),
                quantity=Decimal("1"),
                movement_date=timezone.localdate(),
                project=self.project_b,
                material_name="Blocked Cross Tenant Material",
                supplier_name="Supplier B",
                supplier_phone="0500000003",
                unit=self.unit_b,
            )
        self.assertFalse(
            StockItem.objects.for_company(self.company_b).filter(
                material_name="Blocked Cross Tenant Material"
            ).exists()
        )

    def test_duplicate_identity_validation_is_company_scoped(self):
        response = self.client.post(
            reverse("projects:create"),
            {"code": "shared-01", "name": "Duplicate A", "status": Project.Status.ACTIVE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists in this company")
        self.assertEqual(Project.objects.for_company(self.company_a).filter(code="SHARED-01").count(), 1)

        response = self.client.post(
            reverse("inventory:units"),
            {"name": "Piece", "symbol": "pc", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already exists in this company", status_code=400)

    def test_transfer_line_rejects_cross_company_stock_records(self):
        office = InventoryLocation.objects.create(
            company=self.company_a,
            code="OFFICE-A",
            name="Company A Office",
            location_type=InventoryLocation.Type.OFFICE,
        )
        transfer = StockTransfer.objects.create(
            company=self.company_a,
            idempotency_key=uuid.uuid4(),
            source_location=self.item_a.location,
            destination_location=office,
            transfer_date=timezone.localdate(),
            created_by=self.user_a,
        )
        line = StockTransferLine(
            transfer=transfer,
            source_stock_item=self.item_b,
            outcome=StockTransferLine.Outcome.LOST,
            quantity=Decimal("1"),
            source_condition_snapshot=self.item_b.condition,
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_django_admin_changelists_are_scoped_to_active_company(self):
        ExportAudit.objects.create(
            company=self.company_a,
            dataset=ExportAudit.Dataset.INVENTORY,
            file_format=ExportAudit.Format.CSV,
            scope_label="Company A export",
            created_by=self.admin_a,
        )
        ExportAudit.objects.create(
            company=self.company_b,
            dataset=ExportAudit.Dataset.INVENTORY,
            file_format=ExportAudit.Format.CSV,
            scope_label="Company B export",
            created_by=self.user_b,
        )
        SavedView.objects.create(
            company=self.company_a,
            owner=self.admin_a,
            name="Company A saved view",
            view_type=SavedView.ViewType.INVENTORY,
            query_params={},
        )
        SavedView.objects.create(
            company=self.company_b,
            owner=self.user_b,
            name="Company B saved view",
            view_type=SavedView.ViewType.INVENTORY,
            query_params={},
        )

        self.client.force_login(self.admin_a)
        project_admin = self.client.get(reverse("admin:projects_project_changelist"))
        self.assertContains(project_admin, "Company A Project")
        self.assertNotContains(project_admin, "Company B Project")

        export_admin = self.client.get(reverse("admin:data_exchange_exportaudit_changelist"))
        self.assertContains(export_admin, "Company A export")
        self.assertNotContains(export_admin, "Company B export")

        saved_admin = self.client.get(reverse("admin:explorer_savedview_changelist"))
        self.assertContains(saved_admin, "Company A saved view")
        self.assertNotContains(saved_admin, "Company B saved view")
