import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project
from apps.core.tests.tenant import grant_company_access, primary_company

User = get_user_model()


class ProjectModelTests(TestCase):
    def setUp(self):
        self.company = primary_company()

    def test_project_code_and_display_text_are_normalized(self):
        project = Project.objects.create(company=self.company, code=" aramco-01 ", name="  Aramco   Utilities  ")
        self.assertEqual(project.code, "ARAMCO-01")
        self.assertEqual(project.name, "Aramco Utilities")

    def test_completion_date_cannot_precede_start_date(self):
        project = Project(
            company=self.company,
            code="DATE-01",
            name="Date Test",
            start_date=date(2026, 8, 10),
            expected_completion_date=date(2026, 8, 1),
        )
        with self.assertRaises(ValidationError):
            project.full_clean()


class ProjectWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-password",
        )
        self.company = primary_company()
        grant_company_access(self.user, company=self.company)
        grant_company_access(self.admin, company=self.company)
        self.client.force_login(self.user)

    def test_storekeeper_can_create_project(self):
        response = self.client.post(
            reverse("projects:create"),
            {
                "code": "neom-04",
                "name": "NEOM Site Works",
                "client_name": "NEOM",
                "location": "Tabuk",
                "status": Project.Status.ACTIVE,
            },
        )
        self.assertRedirects(response, reverse("projects:list"))
        project = Project.objects.get(code="NEOM-04")
        self.assertEqual(project.created_by, self.user)
        self.assertEqual(project.updated_by, self.user)

    def test_project_detail_paginates_stock_records(self):
        from apps.inventory.models import StockItem, Unit

        project = Project.objects.create(company=self.company, code="PAGE-01", name="Pagination Project")
        unit = Unit.objects.get(normalized_name="piece")
        StockItem.objects.bulk_create(
            [
                StockItem(
                    project=project,
                    material_name=f"Material {index:03d}",
                    normalized_material_name=f"material {index:03d}",
                    supplier_name=f"Supplier {index:03d}",
                    normalized_supplier_name=f"supplier {index:03d}",
                    supplier_phone=f"+9665000{index:04d}",
                    normalized_supplier_phone=f"9665000{index:04d}",
                    unit=unit,
                )
                for index in range(55)
            ]
        )
        response = self.client.get(reverse("projects:detail", args=[project.code]))
        self.assertEqual(len(response.context["stock_items"]), 50)
        self.assertTrue(response.context["is_paginated"])

    def test_project_list_supports_search_and_status_filter(self):
        Project.objects.create(company=self.company, code="ACTIVE-01", name="Active Project")
        Project.objects.create(company=self.company,
            code="DONE-01",
            name="Completed Project",
            status=Project.Status.COMPLETED,
            end_date=date(2026, 8, 31),
        )
        response = self.client.get(
            reverse("projects:list"),
            {"q": "completed", "status": Project.Status.COMPLETED},
        )
        self.assertContains(response, "DONE-01")
        self.assertNotContains(response, "ACTIVE-01")
        self.assertContains(response, "data-live-filter-search")
        self.assertContains(response, "data-filter-results")

    def test_project_detail_defaults_to_active_records_and_can_show_archived(self):
        from apps.inventory.models import StockItem, Unit

        project = Project.objects.create(company=self.company, code="LIFE-01", name="Lifecycle Project")
        unit = Unit.objects.get(normalized_name="piece")
        active = StockItem.objects.create(
            project=project,
            material_name="Active Material",
            supplier_name="Active Supplier",
            supplier_phone="+966 50 100 1000",
            unit=unit,
        )
        archived = StockItem.objects.create(
            project=project,
            material_name="Archived Material",
            supplier_name="Archived Supplier",
            supplier_phone="+966 50 200 2000",
            unit=unit,
            status=StockItem.Status.ARCHIVED,
        )

        response = self.client.get(reverse("projects:detail", args=[project.code]))
        self.assertContains(response, active.material_name)
        self.assertNotContains(response, archived.material_name)

        response = self.client.get(
            reverse("projects:detail", args=[project.code]),
            {"record_status": StockItem.Status.ARCHIVED},
        )
        self.assertContains(response, archived.material_name)
        self.assertNotContains(response, active.material_name)

    def test_project_with_positive_stock_cannot_be_completed(self):
        from apps.inventory.models import Unit
        from apps.inventory.services.stock import add_stock

        project = Project.objects.create(company=self.company, code="LIVE-01", name="Live Project")
        unit = Unit.objects.get(normalized_name="bag")
        add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            movement_date=timezone.localdate(),
            project=project,
            material_name="Cement",
            supplier_name="Supplier",
            supplier_phone="+966 50 111 2233",
            unit=unit,
        )
        project.status = Project.Status.COMPLETED
        project.end_date = date(2026, 8, 31)
        with self.assertRaises(ValidationError):
            project.save()


    def test_project_archive_with_stock_preserves_exact_status_for_restore(self):
        from apps.inventory.models import StockItem, Unit
        from apps.projects.services import archive_project, restore_project_archive
        from apps.accounts.models import CompanyMembership

        project = Project.objects.create(company=self.company, code="LIFE-04", name="Reversible Project", status=Project.Status.ON_HOLD)
        unit = Unit.objects.get(normalized_name="piece")
        StockItem.objects.create(
            project=project, material_name="Stored Cable", supplier_name="Supplier",
            supplier_phone="0500000999", unit=unit, current_quantity=Decimal("2"),
        )
        membership = CompanyMembership.objects.get(company=self.company, user=self.admin)
        project = archive_project(actor_membership=membership, project_id=project.pk, reason="Pause master")
        self.assertEqual(project.status, Project.Status.ARCHIVED)
        self.assertEqual(project.archive_previous_status, Project.Status.ON_HOLD)
        project = restore_project_archive(actor_membership=membership, project_id=project.pk)
        self.assertEqual(project.status, Project.Status.ON_HOLD)
        self.assertEqual(project.archive_previous_status, "")

    def test_project_lifecycle_requires_inventory_management_authority(self):
        project = Project.objects.create(company=self.company, code="LIFE-02", name="Lifecycle Controls")
        status_url = reverse("projects:status", kwargs={"code": project.code})
        delete_url = reverse("projects:delete", kwargs={"code": project.code})

        self.assertEqual(
            self.client.post(status_url, {"action": "archive", "reason": "No longer used"}).status_code,
            403,
        )
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.ACTIVE)

        self.client.force_login(self.admin)
        response = self.client.post(status_url, {"action": "archive", "reason": "No longer used"})
        self.assertRedirects(response, reverse("projects:detail", args=[project.code]))
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.ARCHIVED)
        self.assertIsNotNone(project.archived_at)

        response = self.client.post(
            delete_url,
            {"confirmation": project.code, "reason": "Duplicate", "acknowledge": "yes"},
        )
        self.assertRedirects(response, reverse("projects:list"))
        project.refresh_from_db()
        self.assertIsNotNone(project.deleted_at)

    def test_project_with_inventory_history_can_be_soft_deleted_without_erasing_stock(self):
        from apps.inventory.models import StockItem, Unit

        project = Project.objects.create(company=self.company, code="LIFE-03", name="Protected Project")
        unit = Unit.objects.get(normalized_name="piece")
        stock = StockItem.objects.create(
            project=project,
            material_name="Cable",
            supplier_name="Cable Supplier",
            supplier_phone="0500000222",
            unit=unit,
            current_quantity=Decimal("4"),
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("projects:delete", kwargs={"code": project.code}),
            {
                "confirmation": project.code,
                "reason": "Project cancelled",
                "acknowledge": "yes",
            },
        )
        self.assertRedirects(response, reverse("projects:list"))
        project.refresh_from_db(); stock.refresh_from_db()
        location = project.inventory_location
        location.refresh_from_db()
        self.assertIsNotNone(project.deleted_at)
        self.assertIsNotNone(stock.deleted_at)
        self.assertIsNotNone(location.deleted_at)
        self.assertEqual(stock.deleted_at, project.deleted_at)
        self.assertEqual(stock.purge_after, project.purge_after)
        self.assertEqual(location.purge_after, project.purge_after)
        self.assertEqual(stock.current_quantity, Decimal("4"))
        # Stock quantities/history are preserved while operational inventory masters are recoverably deleted.
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

        trash = self.client.get(reverse("inventory:trash"))
        self.assertContains(trash, project.code)
        self.assertNotContains(trash, stock.material_name)
        response = self.client.post(
            reverse("inventory:trash_restore", args=["project", project.code])
        )
        self.assertRedirects(response, reverse("inventory:trash"))
        project.refresh_from_db(); stock.refresh_from_db(); location.refresh_from_db()
        self.assertIsNone(project.deleted_at)
        self.assertIsNone(stock.deleted_at)
        self.assertIsNone(location.deleted_at)
