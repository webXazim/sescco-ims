from hashlib import sha256
from pathlib import Path

from django.test import SimpleTestCase


class BrandingMigrationLineageTests(SimpleTestCase):
    def test_released_0003_is_immutable_and_0004_is_forward_repair(self):
        root = Path(__file__).resolve().parents[3]
        migration_0003 = root / "apps/core/migrations/0003_company_document_branding.py"
        migration_0004 = root / "apps/core/migrations/0004_company_document_branding_lineage_repair.py"

        self.assertEqual(
            sha256(migration_0003.read_bytes()).hexdigest(),
            "4bbb41ca7660c1b4a675c646235aca8ca6e816d93d9fa2039378f294f5e3da1d",
        )
        repair = migration_0004.read_text(encoding="utf-8")
        self.assertIn('dependencies = [("core", "0003_company_document_branding")]', repair)
        self.assertIn("migrations.SeparateDatabaseAndState", repair)
        self.assertIn('BRANDING_MODE_COLUMN = "document_branding_mode"', repair)
