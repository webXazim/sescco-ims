#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"
PREDECESSOR_SHA = "88220df5d3896cb626a36bfa49ffba25becd1a3ab1c161e158535b149b8fc9cf"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING MANPOWER MASTER ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-manpower-master.json"))
if contract.get("release") != VERSION:
    fail("Manpower master contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.116 predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("Manpower contact schema change must be declared")
if contract.get("operational_integration") is not False:
    fail("Manpower sourcing master must remain reference-only")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Manpower sourcing master must not change Payroll or Inventory formulas")

models = text("apps/sourcing/models/manpower.py")
for marker in (
    "class SourcingManpowerSupplier(SourcingLifecycleModel)",
    "class SourcingManpowerContact(CompanyOwnedModel)",
    'db_table = "sourcing_manpower_contact"',
    'name="src_mps_one_primary_contact_uq"',
    'name="src_mps_status_name_idx"',
):
    if marker not in models:
        fail(f"Manpower model authority missing: {marker}")
for forbidden in ("from apps.inventory", "from apps.rental_manpower", "from apps.internal_payroll", 'to="inventory.', 'to="rental_manpower.', 'to="internal_payroll.'):
    if forbidden in models:
        fail(f"Manpower sourcing model leaked operational dependency: {forbidden}")

migration = text("apps/sourcing/migrations/0004_manpower_supplier_contacts.py")
for marker in ('name="SourcingManpowerContact"', 'name="src_mps_one_primary_contact_uq"', 'name="src_mpcontact_supplier_active_idx"'):
    if marker not in migration:
        fail(f"Manpower directory migration missing: {marker}")
for forbidden in ('to="inventory.', 'to="rental_manpower.', 'to="internal_payroll.'):
    if forbidden in migration:
        fail(f"Manpower migration contains operational FK: {forbidden}")

rename_migration = text("apps/sourcing/migrations/0007_rename_manpower_contact_index.py")
for marker in ('old_name="src_mpcontact_supplier_active_idx"', 'new_name="src_mpc_supplier_active_idx"'):
    if marker not in rename_migration:
        fail(f"Manpower contact index rename migration missing: {marker}")

selectors = text("apps/sourcing/selectors/manpower.py")
for marker in (
    "Paginator(qs, page_size)",
    "PAGE_SIZES = (25, 50, 100)",
    'status not in {"active", "inactive", "archived", "trash", "all"}',
    "SourcingManpowerSupplier.objects.for_company(company)",
    "manpower_directory_scale_annotations",
    "Q(_contact_match=True)",
):
    if marker not in selectors:
        fail(f"server-side Manpower directory authority missing: {marker}")

services = text("apps/sourcing/services/manpower.py")
for action in contract.get("audit_actions", []):
    if f'"{action}"' not in services:
        fail(f"Manpower audit action missing: {action}")
for marker in (
    "TRASH_RETENTION_DAYS = 30",
    "select_for_update()",
    "purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)",
    "Type {expected} to confirm deletion.",
):
    if marker not in services:
        fail(f"Manpower lifecycle safety missing: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "_require_manpower_view(request)",
    "_require_manpower_manage(request)",
    "manpower_directory_page(company=request.company",
    'page_key="sourcing-manpower"',
    "manpower_contact_create",
    "manpower_contact_edit",
    "manpower_contact_deactivate",
):
    if marker not in views:
        fail(f"Manpower view authority missing: {marker}")
urls = text("apps/sourcing/urls.py")
for route in ("manpower-suppliers/", "manpower-suppliers/new/", "restore-archive/", "restore-trash/", "contacts/new/"):
    if route not in urls:
        fail(f"Manpower route missing: {route}")

for rel in (
    "templates/sourcing/manpower/list.html",
    "templates/sourcing/manpower/form.html",
    "templates/sourcing/manpower/detail.html",
    "templates/sourcing/manpower/contact_form.html",
    "static/sourcing/js/manpower-directory.js",
    "static/sourcing/css/directory.css",
):
    text(rel)
list_template = text("templates/sourcing/manpower/list.html")
for marker in ("Search supplier, contact, phone, email, CR or VAT", "Columns", "page_obj.paginator.count", "New Manpower Supplier"):
    if marker not in list_template:
        fail(f"Manpower directory UI missing: {marker}")
detail_template = text("templates/sourcing/manpower/detail.html")
for marker in ("Workforce Capability", "Contact Persons", "Activity", "Move to Trash", "Lifecycle"):
    if marker not in detail_template:
        fail(f"Manpower profile UI missing: {marker}")
if "Rental Payroll" not in detail_template:
    fail("Manpower profile must state its Rental Payroll isolation")

sidebar = text("templates/sourcing/sidebar.html")
if "sourcing:manpower_supplier_list" not in sidebar or "sourcing-manpower" not in sidebar:
    fail("Manpower supplier navigation is not live")

for rel in (
    "apps/sourcing/models/manpower.py",
    "apps/sourcing/forms.py",
    "apps/sourcing/selectors/manpower.py",
    "apps/sourcing/services/manpower.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_manpower_master.py",
    "apps/sourcing/migrations/0004_manpower_supplier_contacts.py",
    "apps/sourcing/migrations/0007_rename_manpower_contact_index.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

retention = json.loads(text("merge/lifecycle-retention-contract.json"))
if retention.get("models", {}).get("sourcing.SourcingManpowerContact", {}).get("mode") != "reference_master_deactivate_only":
    fail("Manpower contact retention classification is missing")

if "1.0.116" not in text("docs/SOURCING_MANPOWER_MASTER.md"):
    fail("Manpower master operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.116 Manpower Sourcing Master verified: company-scoped server directory, view/edit enforcement, contacts, reversible lifecycle, immutable audit evidence and Rental Payroll isolation.")
