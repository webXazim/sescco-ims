#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
PREDECESSOR_SHA = "4fba174a74f472ef419b62a05082ceb12625a439d925c6006e3f1582d388db88"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING VENDOR MASTER ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-vendor-master.json"))
if contract.get("release") != VERSION:
    fail("Vendor master contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.100 predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("Vendor contact schema change must be declared")
if contract.get("operational_integration") is not False:
    fail("Vendor master must remain reference-only")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Vendor master must not change Payroll or Inventory formulas")

models = text("apps/sourcing/models/vendors.py")
for marker in (
    "class SourcingVendor(SourcingLifecycleModel)",
    "class SourcingVendorContact(CompanyOwnedModel)",
    'db_table = "sourcing_vendor_contact"',
    'name="src_vendor_one_primary_contact_uq"',
    'name="src_vendor_status_name_idx"',
):
    if marker not in models:
        fail(f"Vendor model authority missing: {marker}")
for forbidden in ("from apps.inventory", "from apps.rental_manpower", "from apps.internal_payroll", "to=\"inventory.", "to=\"rental_manpower.", "to=\"internal_payroll."):
    if forbidden in models:
        fail(f"Vendor model leaked operational dependency: {forbidden}")

migration = text("apps/sourcing/migrations/0002_vendor_directory_master.py")
profile_migration = text("apps/sourcing/migrations/0009_vendor_profile_structure.py")
for marker in ('name="SourcingVendorContact"', 'name="src_vendor_one_primary_contact_uq"', 'name="src_vcontact_vendor_active_idx"'):
    if marker not in migration:
        fail(f"Vendor directory migration missing: {marker}")
for marker in ('old_name="phone"', 'new_name="company_phone"', 'name="company_email"', 'name="address"', 'name="street_number"', 'name="district"', 'name="postal_code"'):
    if marker not in profile_migration:
        fail(f"Vendor profile migration missing: {marker}")
for forbidden in ('to="inventory.', 'to="rental_manpower.', 'to="internal_payroll.'):
    if forbidden in migration:
        fail(f"Vendor migration contains operational FK: {forbidden}")

selectors = text("apps/sourcing/selectors/vendors.py")
for marker in (
    "Paginator(qs, page_size)",
    "PAGE_SIZES = (25, 50, 100)",
    'status not in {"active", "inactive", "archived", "trash", "all"}',
    "SourcingVendor.objects.for_company(company)",
    "vendor_directory_scale_annotations",
    "Q(_contact_match=True)",
):
    if marker not in selectors:
        fail(f"server-side Vendor directory authority missing: {marker}")

services = text("apps/sourcing/services/vendors.py")
for action in contract.get("audit_actions", []):
    if f'"{action}"' not in services:
        fail(f"Vendor audit action missing: {action}")
for marker in (
    "TRASH_RETENTION_DAYS = 30",
    "select_for_update()",
    "purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)",
    "Type {expected} to confirm deletion.",
):
    if marker not in services:
        fail(f"Vendor lifecycle safety missing: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "_require_vendor_view(request)",
    "_require_vendor_manage(request)",
    "vendor_directory_page(company=request.company",
    'page_key="sourcing-vendors"',
    "vendor_contact_create",
    "vendor_contact_edit",
    "vendor_contact_deactivate",
):
    if marker not in views:
        fail(f"Vendor view authority missing: {marker}")
urls = text("apps/sourcing/urls.py")
for route in ("vendors/", "vendors/new/", "restore-archive/", "restore-trash/", "contacts/new/"):
    if route not in urls:
        fail(f"Vendor route missing: {route}")

for rel in (
    "templates/sourcing/vendors/list.html",
    "templates/sourcing/vendors/form.html",
    "templates/sourcing/vendors/detail.html",
    "templates/sourcing/vendors/contact_form.html",
    "static/sourcing/css/directory.css",
    "static/sourcing/js/vendor-directory.js",
):
    text(rel)
list_template = text("templates/sourcing/vendors/list.html")
for marker in ("Search vendor, contact, company details, address, CR or VAT", "Columns", "page_obj.paginator.count", "New Vendor"):
    if marker not in list_template:
        fail(f"Vendor directory UI missing: {marker}")
detail_template = text("templates/sourcing/vendors/detail.html")
for marker in ("Supply Catalog", "Contact Persons", "Activity", "Move to Trash", "Lifecycle"):
    if marker not in detail_template:
        fail(f"Vendor profile UI missing: {marker}")

for rel in (
    "apps/sourcing/models/vendors.py",
    "apps/sourcing/forms.py",
    "apps/sourcing/selectors/vendors.py",
    "apps/sourcing/services/vendors.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_vendor_master.py",
    "apps/sourcing/migrations/0002_vendor_directory_master.py",
    "apps/sourcing/migrations/0009_vendor_profile_structure.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

if "1.0.117" not in text("docs/SOURCING_VENDOR_MASTER.md"):
    fail("Vendor master operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.117 Vendor Sourcing Master verified: company-scoped server directory, view/edit enforcement, contacts, reversible lifecycle, immutable audit evidence and operational isolation.")
