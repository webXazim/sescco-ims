#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.113"
PREDECESSOR = "1.0.92-rental-supervisor-foreman-scoped-access"
PREDECESSOR_SHA256 = "ec1388afc1833098292fc59fd9b93b3d92734f4be4e087584690943d39be2763"
STOREKEEPER_PERMISSIONS = {
    "inventory.dashboard.view",
    "inventory.stock.view",
    "inventory.stock.receive",
    "inventory.stock.issue",
    "inventory.stock.transfer",
    "inventory.movements.view",
    "inventory.projects.view",
    "inventory.suppliers.view",
    "inventory.locations.view",
    "inventory.export.execute",
    "shared.search.use",
}
FORBIDDEN = {
    "inventory.stock.adjust",
    "inventory.movements.reverse",
    "inventory.projects.manage",
    "inventory.suppliers.manage",
    "inventory.locations.manage",
    "inventory.import.execute",
    "shared.archive.view",
    "shared.archive.manage",
    "shared.trash.view",
    "shared.trash.manage",
}


def fail(message: str) -> None:
    raise SystemExit(f"INVENTORY STOREKEEPER SCOPE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/inventory-storekeeper-scope.json"))
if contract.get("release") != VERSION:
    fail("contract release does not match VERSION")
if contract.get("schema_change") is not True:
    fail("Storekeeper grant reconciliation must remain migration-controlled")
if contract.get("inventory_quantity_formula_change") is not False or contract.get("payroll_formula_change") is not False:
    fail("Storekeeper access release must not change quantity or Payroll formulas")
profile = contract.get("profile") or {}
if profile.get("classification") != "storekeeper" or profile.get("system_profile_key") != "role-storekeeper":
    fail("Storekeeper profile identity changed")
if set(profile.get("permissions") or []) != STOREKEEPER_PERMISSIONS:
    fail("Storekeeper profile must contain exactly the operational permission set")
if not FORBIDDEN.issubset(set(profile.get("prohibited_by_default") or [])):
    fail("Storekeeper manager-only permission boundary is incomplete")
predecessor = contract.get("predecessor") or {}
if predecessor.get("release") != PREDECESSOR or predecessor.get("archive_sha256") != PREDECESSOR_SHA256:
    fail("Storekeeper release is not bound to the exact 1.0.92 predecessor archive")
scope = contract.get("scope_contract") or {}
for key in (
    "project_backed_location_requires_both_scopes",
    "office_location_requires_location_scope",
    "transfer_requires_source_and_destination_in_scope",
    "stock_queries_scoped",
    "movement_queries_scoped",
    "dashboard_scoped",
    "exports_scoped",
):
    if scope.get(key) is not True:
        fail(f"scope contract lost {key}")

catalog = text("apps/accounts/access_catalog.py")
parts = catalog.split("if role == AccessRole.STOREKEEPER:", 1)
if len(parts) != 2:
    fail("dedicated Storekeeper Access Profile template is missing")
block = parts[1].split("if role == AccessRole.RENTAL_SUPERVISOR:", 1)[0]
for permission in STOREKEEPER_PERMISSIONS:
    suffix = permission.upper().replace(".", "_")
    if suffix not in block:
        fail(f"Storekeeper profile template missing {permission}")
for enum_name in (
    "INVENTORY_STOCK_ADJUST", "INVENTORY_MOVEMENTS_REVERSE", "INVENTORY_IMPORT_EXECUTE",
    "INVENTORY_PROJECTS_MANAGE", "INVENTORY_SUPPLIERS_MANAGE", "INVENTORY_LOCATIONS_MANAGE",
    "SHARED_ARCHIVE_VIEW", "SHARED_TRASH_VIEW",
):
    if enum_name in block:
        fail(f"Storekeeper template improperly grants {enum_name}")

migration = text("apps/accounts/migrations/0009_storekeeper_scoped_authority.py")
for marker in (
    '("accounts", "0008_rental_supervisor_profile")',
    '"inventory.stock.receive"', '"inventory.stock.issue"', '"inventory.stock.transfer"',
    'migrations.RunPython(reconcile_storekeeper_profiles, noop_reverse)',
):
    if marker not in migration:
        fail(f"0009 Storekeeper migration marker missing: {marker}")

access = text("apps/inventory/access.py")
for marker in (
    "def location_in_inventory_scope(", "membership_allows_inventory_location", "membership_allows_project",
    "def project_in_inventory_scope(", "def restrict_inventory_projects(",
    "def restrict_inventory_location_queryset(", "def restrict_inventory_stock(",
    "def restrict_inventory_movements(", "def restrict_inventory_transfers(",
    "source_location_id__in=source_ids", "destination_location_id__in=destination_ids",
):
    if marker not in access:
        fail(f"Inventory scope authority marker missing: {marker}")

stock = text("apps/inventory/services/stock.py")
for marker in (
    "AccessPermission.INVENTORY_STOCK_RECEIVE", "AccessPermission.INVENTORY_STOCK_ISSUE",
    "AccessPermission.INVENTORY_STOCK_ADJUST", "AccessPermission.INVENTORY_MOVEMENTS_REVERSE",
    "_require_project_scope(membership, project)", "_require_stock_scope(membership, stock_item)",
):
    if marker not in stock:
        fail(f"stock service exact-permission/scope marker missing: {marker}")
transfers = text("apps/inventory/services/transfers.py")
for marker in (
    "AccessPermission.INVENTORY_STOCK_TRANSFER", "AccessPermission.INVENTORY_MOVEMENTS_REVERSE",
    "location_in_inventory_scope(membership, source_location)",
    "location_in_inventory_scope(membership, destination_location)",
    "Both transfer locations must be inside your assigned Inventory scope.",
):
    if marker not in transfers:
        fail(f"transfer authority marker missing: {marker}")

views = text("apps/inventory/views.py")
for marker in (
    "InventoryPermissionRequiredMixin", "AccessPermission.INVENTORY_STOCK_VIEW",
    "AccessPermission.INVENTORY_STOCK_RECEIVE", "AccessPermission.INVENTORY_STOCK_ISSUE",
    "AccessPermission.INVENTORY_STOCK_TRANSFER", "AccessPermission.INVENTORY_STOCK_ADJUST",
    "AccessPermission.INVENTORY_MOVEMENTS_VIEW", "AccessPermission.INVENTORY_SUPPLIERS_VIEW",
    "AccessPermission.INVENTORY_LOCATIONS_VIEW", "restrict_inventory_stock(",
    "restrict_inventory_movements(", "restrict_inventory_transfers(",
    "restrict_inventory_location_queryset(",
):
    if marker not in views:
        fail(f"Inventory view authority marker missing: {marker}")
projects = text("apps/projects/views.py")
for marker in (
    "AccessPermission.INVENTORY_PROJECTS_VIEW", "AccessPermission.INVENTORY_PROJECTS_MANAGE",
    "restrict_inventory_projects(",
):
    if marker not in projects:
        fail(f"Project scope marker missing: {marker}")
exports = text("apps/data_exchange/services/exporting.py") + text("apps/data_exchange/views.py")
for marker in (
    "membership=request.company_membership", "restrict_inventory_stock(",
    "AccessPermission.INVENTORY_EXPORT_EXECUTE", "restrict_inventory_projects(",
):
    if marker not in exports:
        fail(f"scoped export marker missing: {marker}")
context = text("apps/core/context_processors.py")
for marker in (
    "restrict_inventory_stock(", "restrict_inventory_projects(", "restrict_inventory_location_queryset(",
    "AccessPermission.SHARED_ARCHIVE_VIEW", "AccessPermission.SHARED_TRASH_VIEW",
):
    if marker not in context:
        fail(f"scoped navigation counter marker missing: {marker}")

for rel in ("templates/partials/sidebar.html", "templates/partials/topbar.html", "templates/partials/mobile_nav.html", "templates/partials/stock_actions_menu.html"):
    ui = text(rel)
    if "ACCESS_CONTEXT.effective_access.permissions" not in ui:
        fail(f"Inventory UI does not consume the server permission snapshot: {rel}")

# Regression evidence is mandatory even in static build environments.
tests_rel = "apps/inventory/tests/test_storekeeper_scope.py"
tests = text(tests_rel)
tree = ast.parse(tests)
discovered = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
required_tests = {
    "test_storekeeper_profile_is_exact_and_excludes_high_risk_permissions",
    "test_project_location_and_stock_queries_apply_both_scopes",
    "test_direct_stock_page_cannot_open_out_of_scope_record",
    "test_storekeeper_can_issue_in_scope_but_not_out_of_scope",
    "test_storekeeper_transfer_requires_both_locations_in_scope",
    "test_storekeeper_cannot_adjust_stock_or_open_imports",
    "test_storekeeper_cannot_manage_projects_suppliers_or_units",
    "test_dashboard_and_exports_do_not_leak_blocked_project",
}
if not required_tests.issubset(discovered):
    fail(f"Storekeeper regression evidence incomplete: {sorted(required_tests - discovered)}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-inventory-storekeeper-scope.py" not in text(rel):
        fail(f"{rel} does not enforce the Storekeeper scope gate")

print("Verified SESCCO MS 1.0.113 Inventory Storekeeper scoped authority: exact operational profile, Project+Location intersection, scoped stock/movements/dashboard/exports, two-end transfer validation, and manager-only corrective/master/import/lifecycle controls.")
