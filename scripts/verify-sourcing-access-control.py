#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
PREDECESSOR_SHA = "3de0aa62e4045695764b4deb6378d8ea32b708afdd541612b8c2a7fb5e906326"
EXPECTED = {
    "sourcing.vendors.view",
    "sourcing.vendors.manage",
    "sourcing.manpower.view",
    "sourcing.manpower.manage",
    "sourcing.masters.view",
    "sourcing.masters.manage",
    "sourcing.export.execute",
}


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING ACCESS ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-access-control.json"))
if contract.get("release") != VERSION:
    fail("Sourcing access contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.99 predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("1.0.115 must declare the Accounts permission-constraint schema change")
if contract.get("module_access_enabled") is not True:
    fail("Sourcing module permission cutover is not enabled")
if set(contract.get("permissions") or []) != EXPECTED:
    fail("Sourcing permission catalog changed")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Sourcing access cutover must not alter Payroll or Inventory formulas")

catalog = text("apps/accounts/access_catalog.py")
for permission in EXPECTED:
    if f'"{permission}"' not in catalog:
        fail(f"AccessPermission missing {permission}")
if "SOURCING_MODULE_PERMISSIONS" not in catalog:
    fail("Sourcing module permission bundle missing")

profiles = text("apps/accounts/access_profiles.py")
for action_marker, view_marker in {
    "AccessPermission.SOURCING_VENDORS_MANAGE.value": "AccessPermission.SOURCING_VENDORS_VIEW.value",
    "AccessPermission.SOURCING_MANPOWER_MANAGE.value": "AccessPermission.SOURCING_MANPOWER_VIEW.value",
    "AccessPermission.SOURCING_MASTERS_MANAGE.value": "AccessPermission.SOURCING_MASTERS_VIEW.value",
}.items():
    if action_marker not in profiles or view_marker not in profiles:
        fail(f"Access Profile dependency missing: {action_marker} -> {view_marker}")
for marker in (
    '"sourcing": "Sourcing Directory"',
    "Sourcing export requires at least one Sourcing view permission.",
):
    if marker not in profiles:
        fail(f"Sourcing Access Profile catalog validation missing: {marker}")

modules = text("apps/accounts/modules.py")
for marker in (
    "membership_has_any_sourcing_access",
    "return membership_has_any_sourcing_access(membership)",
    'normalized.startswith("/app/sourcing/")',
    'return "sourcing:home"',
):
    if marker not in modules:
        fail(f"Sourcing module permission gate missing: {marker}")
if "SOURCING" in modules and "return False" in modules.split("if value is PlatformModule.SOURCING:", 1)[-1].split("return membership_has_permission", 1)[0]:
    fail("Sourcing module still contains the 1.0.99 unconditional fail-closed return")

context = text("apps/accounts/context.py")
for marker in ('PlatformModule.SOURCING', '"label": "Sourcing Directory"', 'reverse("sourcing:home")'):
    if marker not in context:
        fail(f"module switcher lost Sourcing permission-aware registration: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "membership_has_any_sourcing_access",
    "raise PermissionDenied",
    "sourcing_access_context",
):
    if marker not in views:
        fail(f"Sourcing home backend gate missing: {marker}")
access_context = text("apps/sourcing/access.py")
for marker in ('"vendors": {', '"manpower": {', '"masters": {', '"export": membership_can_export_sourcing'):
    if marker not in access_context:
        fail(f"Sourcing template access context missing: {marker}")

access = text("apps/sourcing/access.py")
for marker in (
    "VISIBLE_SOURCING_PERMISSIONS",
    "def membership_can_view_vendor_sourcing",
    "def membership_can_manage_vendor_sourcing",
    "def membership_can_view_manpower_sourcing",
    "def membership_can_manage_manpower_sourcing",
    "def membership_can_view_sourcing_masters",
    "def membership_can_manage_sourcing_masters",
):
    if marker not in access:
        fail(f"Sourcing access helper missing: {marker}")
visibility_body = access.split("def membership_has_any_sourcing_access", 1)[1].split("def membership_can_view_vendor_sourcing", 1)[0]
if "VISIBLE_SOURCING_PERMISSIONS" not in visibility_body or "ALL_SOURCING_PERMISSIONS" in visibility_body:
    fail("Sourcing module visibility must remain fail-closed on read/view permissions only")

migration = text("apps/accounts/migrations/0012_sourcing_access_control_authority.py")
for permission in EXPECTED:
    if repr(permission) not in migration and f'"{permission}"' not in migration:
        fail(f"permission constraint migration missing {permission}")
for marker in (
    'key="role-owner"',
    "SOURCING_OWNER_PERMISSIONS",
    'name="accounts_profile_permission_valid"',
):
    if marker not in migration:
        fail(f"Sourcing access migration missing: {marker}")
for forbidden_key in (
    "role-storekeeper", "role-rental-officer", "role-rental-supervisor", "role-finance",
):
    if re.search(rf'filter\([^\n]*key=["\']{re.escape(forbidden_key)}["\']', migration):
        fail(f"migration must not auto-grant Sourcing to {forbidden_key}")

ui = text("static/platform/js/access-management.js")
for marker in (
    'v.startsWith("sourcing.")',
    '"sourcing.vendors.manage": "sourcing.vendors.view"',
    '"sourcing.manpower.manage": "sourcing.manpower.view"',
):
    if marker not in ui:
        fail(f"Administration Access Profile UI missing Sourcing authority marker: {marker}")
admin_template = text("templates/accounts/administration.html")
if "Vendor Sourcing, Manpower Sourcing" not in admin_template:
    fail("Administration does not explain independent Sourcing assignment")

sourcing_template = text("templates/sourcing/home.html")
base_template = text("templates/sourcing/base.html")
for marker in ("SOURCING_ACCESS.vendors.view", "SOURCING_ACCESS.manpower.view", "SOURCING_ACCESS.masters.view"):
    if marker not in sourcing_template and marker not in base_template:
        fail(f"Sourcing shell does not hide unauthorized area: {marker}")
if "Reference-only supplier intelligence" not in base_template:
    fail("Sourcing shell does not state the reference-only boundary")

for rel in (
    "apps/accounts/access_catalog.py",
    "apps/accounts/access_profiles.py",
    "apps/accounts/modules.py",
    "apps/accounts/context.py",
    "apps/accounts/views.py",
    "apps/accounts/migrations/0012_sourcing_access_control_authority.py",
    "apps/sourcing/access.py",
    "apps/sourcing/views.py",
    "apps/sourcing/tests/test_access_control.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

if "1.0.115" not in text("docs/SOURCING_ACCESS_CONTROL.md"):
    fail("Sourcing access-control guide is not version-bound")

print("PASS: SESCCO MS 1.0.115 Sourcing Access-Control Authority verified: Vendor/Manpower/Master view-edit separation, owner-only builtin grant, permission-aware module visibility and backend enforcement.")
