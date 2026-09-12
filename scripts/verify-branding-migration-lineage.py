#!/usr/bin/env python3
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_0003_SHA256 = "4bbb41ca7660c1b4a675c646235aca8ca6e816d93d9fa2039378f294f5e3da1d"

migration_0003 = ROOT / "apps/core/migrations/0003_company_document_branding.py"
migration_0004 = ROOT / "apps/core/migrations/0004_company_document_branding_lineage_repair.py"
model_path = ROOT / "apps/core/models/settings.py"

actual = sha256(migration_0003.read_bytes()).hexdigest()
if actual != ORIGINAL_0003_SHA256:
    raise SystemExit(
        "BRANDING MIGRATION LINEAGE ERROR: core.0003 changed after release; "
        f"expected {ORIGINAL_0003_SHA256}, got {actual}"
    )

repair = migration_0004.read_text(encoding="utf-8")
required_repair_tokens = (
    'dependencies = [("core", "0003_company_document_branding")]',
    "migrations.SeparateDatabaseAndState",
    "_repair_database_schema",
    'BRANDING_MODE_COLUMN = "document_branding_mode"',
    "TYPE varchar(180)",
    'name="document_branding_mode"',
    "max_length=180",
    "validate_document_branding_size",
)
for token in required_repair_tokens:
    if token not in repair:
        raise SystemExit(f"BRANDING MIGRATION LINEAGE ERROR: 0004 missing {token!r}")

model = model_path.read_text(encoding="utf-8")
for token in (
    "document_branding_mode = models.CharField(",
    "max_length=180",
    "validate_document_branding_size",
    "12 * 1024 * 1024",
):
    if token not in model:
        raise SystemExit(f"BRANDING MIGRATION LINEAGE ERROR: settings model missing {token!r}")


release_tasks = (ROOT / "scripts/release-tasks.sh").read_text(encoding="utf-8")
if "run_manage verify_company_settings_schema" not in release_tasks:
    raise SystemExit("BRANDING MIGRATION LINEAGE ERROR: release tasks do not verify the physical branding schema")
if release_tasks.index("run_manage verify_company_settings_schema") > release_tasks.index("seed_payroll_test_data"):
    raise SystemExit("BRANDING MIGRATION LINEAGE ERROR: physical schema verification must run before seed")

print("Company branding migration lineage repair verified.")
