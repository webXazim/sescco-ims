#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
MIGRATION = "apps/accounts/migrations/0014_inventory_manager_import_permission.py"
CONTRACT = "merge/inventory-manager-permission-reconciliation-hotfix.json"
PREDECESSOR_SHA = "2a3d174556821454f1f55013fba26247d2a0dc594f4276fe6aecdb3b7b07ecfb"


def fail(message: str) -> None:
    raise SystemExit(f"INVENTORY MANAGER PERMISSION RECONCILIATION HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        fail(f"missing file: {rel}")
    return p.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read(CONTRACT))
if contract.get("release") != VERSION or contract.get("scope") != "inventory-manager-permission-reconciliation-hotfix":
    fail("hotfix contract identity mismatch")
if contract.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.114 predecessor checksum changed")
if contract.get("migration") != MIGRATION:
    fail("hotfix migration path changed")
if contract.get("profile_key") != "role-inventory-manager" or contract.get("permission") != "inventory.import.execute":
    fail("hotfix authority target changed")
for key in (
    "new_schema_migration", "database_schema_change", "permission_catalog_change",
    "storekeeper_authority_change", "payroll_formula_change", "inventory_quantity_change",
    "sourcing_business_rule_change",
):
    if contract.get(key) is not False:
        fail(f"{key} must remain false")
if contract.get("database_data_change") is not True:
    fail("hotfix must declare the built-in profile data reconciliation")
if contract.get("uses_schema_editor_database_alias") is not True:
    fail("migration must remain database-alias aware")

text = read(MIGRATION)
ast.parse(text, filename=MIGRATION)
for marker in (
    'PROFILE_KEY = "role-inventory-manager"',
    'PERMISSION = "inventory.import.execute"',
    'db = schema_editor.connection.alias',
    'AccessProfile = apps.get_model("accounts", "AccessProfile")',
    'AccessProfilePermission = apps.get_model("accounts", "AccessProfilePermission")',
    '.filter(key=PROFILE_KEY, is_system=True, is_active=True)',
    'AccessProfile.objects.using(db)',
    'AccessProfilePermission.objects.using(db)',
    'ignore_conflicts=True',
    '("accounts", "0013_rename_access_profile_index")',
):
    if marker not in text:
        fail(f"migration safety marker missing: {marker}")
if "role-storekeeper" in text:
    fail("hotfix migration must not mutate Storekeeper authority")

catalog = read("apps/accounts/access_catalog.py")
roles = read("apps/accounts/roles.py")
if 'INVENTORY_IMPORT_EXECUTE = "inventory.import.execute"' not in catalog:
    fail("permission catalog lost inventory.import.execute")
if "Capability.IMPORT_INVENTORY" not in roles:
    fail("Inventory Manager role no longer declares import capability")
if "if Capability.IMPORT_INVENTORY in definition.capabilities:" not in catalog or "permissions.add(AccessPermission.INVENTORY_IMPORT_EXECUTE)" not in catalog:
    fail("authoritative built-in profile mapping no longer derives Inventory import authority")

storekeeper_block = catalog[catalog.index("if role == AccessRole.STOREKEEPER:"):catalog.index("if role == AccessRole.RENTAL_SUPERVISOR:")]
if "INVENTORY_IMPORT_EXECUTE" in storekeeper_block:
    fail("Storekeeper must remain without Inventory import authority")

report = read("apps/core/management/commands/merge_access_report.py")
for marker in ("system_profile_permission_drift", "permissions_for_legacy_role(role)"):
    if marker not in report:
        fail(f"runtime reconciliation gate lost marker: {marker}")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION or release.get("release_type") != "inventory-manager-permission-reconciliation-hotfix":
    fail("release candidate identity mismatch")
if release.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("release candidate predecessor checksum mismatch")
if "scripts/verify-inventory-manager-permission-reconciliation-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not require permission reconciliation verifier")
if "python manage.py merge_access_report --fail-on-errors" not in set(release.get("required_runtime_gates") or []):
    fail("release candidate does not retain runtime access reconciliation")

notes = read("RELEASE_NOTES.md")
if not notes.startswith("# 1.0.115 — Inventory Manager Permission Reconciliation Hotfix\n"):
    fail("release notes do not lead with the 1.0.115 hotfix")
if "SESCCO MS 1.0.115 — Inventory Manager Permission Reconciliation Hotfix" not in read("README.md"):
    fail("README does not identify the 1.0.115 packaged release")

print("Verified SESCCO MS 1.0.115 Inventory Manager permission reconciliation: exact import grant, database-alias-safe forward migration, Storekeeper unchanged, and runtime merge_access_report gate retained.")
