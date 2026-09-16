#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
MIGRATION = "apps/accounts/migrations/0008_rental_supervisor_profile.py"
CONTRACT = "merge/accounts-rental-supervisor-migration-hotfix.json"
PREDECESSOR_SHA = "aa870514601cb796a1f58bd569acd0c527082c411494b07dbcba830ba25a6a41"


def fail(message: str) -> None:
    raise SystemExit(f"ACCOUNTS RENTAL SUPERVISOR MIGRATION HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        fail(f"missing file: {rel}")
    return p.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read(CONTRACT))
if contract.get("release") != VERSION or contract.get("scope") != "accounts-rental-supervisor-migration-hotfix":
    fail("hotfix contract identity mismatch")
if contract.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.113 predecessor checksum changed")
for key in (
    "new_schema_migration",
    "database_schema_change",
    "database_data_change_by_hotfix",
    "permission_catalog_change",
    "payroll_formula_change",
    "inventory_quantity_change",
    "sourcing_business_rule_change",
):
    if contract.get(key) is not False:
        fail(f"{key} must remain false")
if contract.get("uses_schema_editor_database_alias") is not True:
    fail("migration must remain database-alias aware")

text = read(MIGRATION)
ast.parse(text, filename=MIGRATION)
if 'apps.get_model("accounts", "Company")' in text or "apps.get_model('accounts', 'Company')" in text:
    fail("historical migration still resolves Company from accounts")
if 'Company = apps.get_model("core", "Company")' not in text:
    fail("historical migration must resolve Company from core")
if "db = schema_editor.connection.alias" not in text:
    fail("historical data migration must use schema_editor.connection.alias")
for marker in (
    "Company.objects.using(db)",
    "AccessProfile.objects.using(db).update_or_create",
    "AccessProfilePermission.objects.using(db).filter",
    "AccessProfilePermission.objects.using(db).bulk_create",
    "AccessProfile.objects.using(db).filter",
):
    if marker not in text:
        fail(f"database-alias-safe migration marker missing: {marker}")

# The Accounts migration chain already establishes core.Company before 0008.
company_membership = read("apps/accounts/migrations/0003_company_membership.py")
if '("core", "0001_platform_core")' not in company_membership:
    fail("Accounts migration chain no longer guarantees historical core.Company state")
if 'to="core.company"' not in company_membership:
    fail("CompanyMembership historical FK no longer targets core.Company")

# Do not allow the same broken historical lookup elsewhere in migrations.
for p in (ROOT / "apps").glob("*/migrations/*.py"):
    source = p.read_text(encoding="utf-8")
    if 'apps.get_model("accounts", "Company")' in source or "apps.get_model('accounts', 'Company')" in source:
        fail(f"invalid accounts.Company historical lookup remains: {p.relative_to(ROOT)}")

# This hotfix corrects migration code; it must not introduce a new Accounts migration.
if (ROOT / "apps/accounts/migrations/0014_rental_supervisor_migration_hotfix.py").exists():
    fail("hotfix must not add a later migration that cannot repair failing accounts.0008")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION:
    fail("release candidate does not match VERSION")
if "scripts/verify-accounts-rental-supervisor-migration-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not retain the historical migration verifier")
for runtime_gate in (
    "python manage.py check --deploy --fail-level ERROR",
    "python manage.py makemigrations --check --dry-run",
    "python manage.py migrate --plan",
):
    if runtime_gate not in set(release.get("required_runtime_gates") or []):
        fail(f"required runtime gate missing: {runtime_gate}")

if "1.0.115" not in read("docs/ACCOUNTS_RENTAL_SUPERVISOR_MIGRATION_HOTFIX.md"):
    fail("historical hotfix guide is not carried forward to 1.0.115")
if "do not fake it" not in read("docs/ACCOUNTS_RENTAL_SUPERVISOR_MIGRATION_HOTFIX.md").lower():
    fail("operator guide must explicitly prohibit faking accounts.0008")

print("Verified SESCCO MS 1.0.115 Accounts Rental Supervisor historical migration hotfix: core.Company lookup, database-alias-safe RunPython, no new schema migration, and no remaining accounts.Company migration lookup.")
