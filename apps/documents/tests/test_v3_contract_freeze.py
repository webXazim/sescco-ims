from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from apps.documents.models import DocumentType
from apps.documents.services.documents import (
    PROJECT_TIMESHEET_VARIANT,
    SUPPLIER_TIMESHEET_ALIAS,
    SUPPLIER_TIMESHEET_VARIANT,
)
from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetOvertime


class RentalDocumentV3ContractFreezeTests(SimpleTestCase):
    def test_legacy_v2_document_types_remain_available_after_additive_cutover(self):
        legacy = {
            "salary_slip",
            "internal_timesheet",
            "salary_payment_receipt",
            "rental_timesheet",
            "supplier_settlement",
            "supplier_invoice",
            "supplier_payment_receipt",
        }
        current = {value for value, _ in DocumentType.choices}
        self.assertTrue(legacy.issubset(current))
        self.assertEqual(current - legacy, {"supplier_timesheet_pack"})

    def test_supplier_timesheet_alias_and_legacy_variants_are_frozen(self):
        self.assertEqual(SUPPLIER_TIMESHEET_ALIAS, "supplier_timesheet")
        self.assertEqual(SUPPLIER_TIMESHEET_VARIANT, "supplier_timesheet")
        self.assertEqual(PROJECT_TIMESHEET_VARIANT, "project_timesheet")

    def test_rental_timesheet_authority_is_daily_regular_and_monthly_overtime(self):
        entry_fields = {field.name for field in RentalTimesheetEntry._meta.get_fields()}
        overtime_fields = {field.name for field in RentalTimesheetOvertime._meta.get_fields()}
        self.assertIn("work_date", entry_fields)
        self.assertIn("regular_hours", entry_fields)
        self.assertIn("hours", overtime_fields)
        self.assertNotIn("work_date", overtime_fields)
        overtime_unique = {
            tuple(constraint.fields)
            for constraint in RentalTimesheetOvertime._meta.constraints
            if getattr(constraint, "fields", None)
        }
        self.assertIn(("period", "worker"), overtime_unique)

    def test_existing_document_routes_remain_reverseable(self):
        self.assertEqual(reverse("documents:documents-api"), "/api/documents/")
        self.assertEqual(reverse("documents:document-sources-api"), "/api/documents/sources/")
        self.assertEqual(reverse("documents:document-generation-options-api"), "/api/documents/generation-options/")
        self.assertEqual(reverse("documents:document-generation-plan-api"), "/api/documents/generation-plan/")
        self.assertEqual(reverse("documents:document-generation-execute-api"), "/api/documents/generate/")

    def test_document_schema_lineage_keeps_frozen_v2_migrations_and_adds_v3_type_migration(self):
        migration_dir = Path(settings.BASE_DIR) / "apps" / "documents" / "migrations"
        migrations = sorted(path.name for path in migration_dir.glob("[0-9][0-9][0-9][0-9]_*.py"))
        self.assertEqual(
            migrations,
            [
                "0001_initial.py",
                "0002_alter_businessdocument_company_and_more.py",
                "0003_supplier_timesheet_pack_type.py",
            ],
        )
