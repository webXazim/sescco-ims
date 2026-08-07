import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.projects.models import Project

User = get_user_model()


class ProjectModelTests(TestCase):
    def test_project_code_and_display_text_are_normalized(self):
        project = Project.objects.create(code=" aramco-01 ", name="  Aramco   Utilities  ")
        self.assertEqual(project.code, "ARAMCO-01")
        self.assertEqual(project.name, "Aramco Utilities")

    def test_completion_date_cannot_precede_start_date(self):
        project = Project(
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

        project = Project.objects.create(code="PAGE-01", name="Pagination Project")
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
        Project.objects.create(code="ACTIVE-01", name="Active Project")
        Project.objects.create(
            code="DONE-01",
            name="Completed Project",
            status=Project.Status.COMPLETED,
        )
        response = self.client.get(
            reverse("projects:list"),
            {"q": "completed", "status": Project.Status.COMPLETED},
        )
        self.assertContains(response, "DONE-01")
        self.assertNotContains(response, "ACTIVE-01")


    def test_project_detail_defaults_to_active_records_and_can_show_archived(self):
        from apps.inventory.models import StockItem, Unit

        project = Project.objects.create(code="LIFE-01", name="Lifecycle Project")
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

        project = Project.objects.create(code="LIVE-01", name="Live Project")
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
        with self.assertRaises(ValidationError):
            project.save()
