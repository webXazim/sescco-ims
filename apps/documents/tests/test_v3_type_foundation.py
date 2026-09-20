from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.documents.models import DocumentType, production_document_label
from apps.documents.schema import (
    LEGACY_DOCUMENT_SCHEMA_VERSION,
    SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION,
    document_schema_version_for_type,
    validate_supplier_timesheet_pack_snapshot,
)


def _valid_pack_snapshot() -> dict[str, object]:
    return {
        "kind": "supplier_timesheet_pack",
        "document_schema_version": "3.0",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "revision": 6,
        "source": {
            "model": "rental_manpower.rentaltimesheetperiod",
            "id": "11111111-1111-1111-1111-111111111111",
            "status": "locked",
            "revision": 6,
        },
        "project": {"code": "P-001", "name": "Project 001"},
        "supplier": {"code": "SUP-001", "name": "Supplier 001"},
        "summary": {
            "worker_count": 1,
            "regular_hours": "8.00",
            "overtime_hours": "12.00",
            "total_hours": "20.00",
        },
        "workers": [
            {
                "worker_id": "22222222-2222-2222-2222-222222222222",
                "worker_number": "RW-001",
                "worker_name": "Worker 001",
                "trades": ["Mason"],
                "summary": {
                    "regular_hours": "8.00",
                    "overtime_hours": "12.00",
                    "total_hours": "20.00",
                },
                "days": [
                    {
                        "date": "2026-06-01",
                        "day": "Monday",
                        "attendance": "WORK",
                        "regular_hours": "8.00",
                        "trade": "Mason",
                        "note": "",
                    }
                ],
            }
        ],
    }


class SupplierTimesheetPackTypeFoundationTests(SimpleTestCase):
    def test_supplier_timesheet_pack_is_additive_stored_type(self):
        self.assertEqual(DocumentType.SUPPLIER_TIMESHEET_PACK, "supplier_timesheet_pack")
        self.assertEqual(production_document_label(DocumentType.SUPPLIER_TIMESHEET_PACK), "Supplier Monthly Timesheet Pack")

    def test_schema_version_selection_keeps_legacy_v2_and_pack_v3(self):
        self.assertEqual(LEGACY_DOCUMENT_SCHEMA_VERSION, "2.0")
        self.assertEqual(SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION, "3.0")
        self.assertEqual(document_schema_version_for_type(DocumentType.RENTAL_TIMESHEET), "2.0")
        self.assertEqual(document_schema_version_for_type(DocumentType.SUPPLIER_TIMESHEET_PACK), "3.0")

    def test_valid_supplier_timesheet_pack_schema_is_accepted(self):
        validate_supplier_timesheet_pack_snapshot(_valid_pack_snapshot())

    def test_supplier_timesheet_pack_rejects_commercial_fields_recursively(self):
        snapshot = _valid_pack_snapshot()
        snapshot["workers"][0]["summary"]["rate"] = "9.25"  # type: ignore[index]
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(snapshot)

    def test_supplier_timesheet_pack_rejects_invented_daily_overtime(self):
        snapshot = _valid_pack_snapshot()
        snapshot["workers"][0]["days"][0]["overtime_hours"] = "2.00"  # type: ignore[index]
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(snapshot)

    def test_v3_type_migration_is_additive_and_has_no_data_rewrite(self):
        migration = Path(settings.BASE_DIR) / "apps" / "documents" / "migrations" / "0003_supplier_timesheet_pack_type.py"
        payload = migration.read_text(encoding="utf-8")
        self.assertIn('"supplier_timesheet_pack"', payload)
        self.assertIn('name="doc_type_valid"', payload)
        self.assertIn("migrations.RemoveConstraint", payload)
        self.assertIn("migrations.AlterField", payload)
        self.assertIn("migrations.AddConstraint", payload)
        self.assertNotIn("RunPython", payload)
        self.assertNotIn("RunSQL", payload)
