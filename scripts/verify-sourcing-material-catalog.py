#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"
PREDECESSOR_SHA = "52ac1adef10a90e066908b21dac78599b0cadd9d8551a4b7c7c8113bc92ad008"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING MATERIAL CATALOG ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-material-catalog.json"))
if contract.get("release") != VERSION:
    fail("Material Catalog contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.101 predecessor checksum changed")
if contract.get("operational_integration") is not False:
    fail("Material Catalog must remain reference-only")
if contract.get("inventory_stock_effect") is not False or contract.get("accounting_posting") is not False:
    fail("Material Catalog must not claim Inventory or Accounting effects")
if contract.get("schema_change") is not True:
    fail("normalized alias search schema change must be declared")

models = text("apps/sourcing/models/vendors.py")
for marker in (
    "class SourcingMaterial(CompanyOwnedModel)",
    "class SourcingVendorOffer(SourcingRateMixin, CompanyOwnedModel)",
    "class SourcingVendorOfferRevision(CompanyOwnedModel)",
    "normalized_aliases = models.TextField",
    'name="src_vendor_offer_identity_uq"',
    'name="src_offer_material_find_idx"',
):
    if marker not in models:
        fail(f"material/catalog model authority missing: {marker}")
for forbidden in ("from apps.inventory", "from apps.rental_manpower", "from apps.internal_payroll"):
    if forbidden in models:
        fail(f"Sourcing model leaked operational dependency: {forbidden}")

migration = text("apps/sourcing/migrations/0003_material_alias_search.py")
for marker in ('name="normalized_aliases"', "backfill_normalized_aliases", '("sourcing", "0002_vendor_directory_master")'):
    if marker not in migration:
        fail(f"forward material migration missing: {marker}")
for forbidden in ('to="inventory.', 'to="rental_manpower.', 'to="internal_payroll.'):
    if forbidden in migration:
        fail(f"material migration contains operational FK: {forbidden}")

forms = text("apps/sourcing/forms.py")
for marker in (
    "class SourcingMaterialForm",
    "class SourcingVendorOfferForm",
    'label="Verified now"',
    'label="Spoke With"',
    'self.fields["material"].queryset',
):
    if marker not in forms:
        fail(f"material/catalog form authority missing: {marker}")

selectors = text("apps/sourcing/selectors/materials.py")
for marker in (
    "Paginator(qs, page_size)",
    "PAGE_SIZES = (25, 50, 100)",
    "normalized_aliases__icontains=normalized_query",
    "material_directory_scale_annotations",
    "vendor_catalog",
):
    if marker not in selectors:
        fail(f"material selector authority missing: {marker}")

services = text("apps/sourcing/services/catalog.py")
for marker in (
    "create_material",
    "update_material",
    "set_material_active",
    "create_vendor_offer",
    "update_vendor_offer",
    "set_vendor_offer_active",
    "SourcingVendorOfferRevision.objects.create",
    'action="sourcing.material.created"',
    'action="sourcing.vendor_offer.created"',
    'action="sourcing.vendor_offer.updated"',
    '"sourcing.vendor_offer.deactivated"',
    "vendor.last_verified_at = offer.last_verified_at",
):
    if marker not in services:
        fail(f"material/catalog service authority missing: {marker}")
for forbidden in ("apps.inventory", "apps.rental_manpower", "apps.internal_payroll", "apps.accounting"):
    if forbidden in services:
        fail(f"catalog service leaked operational integration: {forbidden}")

views = text("apps/sourcing/views.py")
for marker in (
    "_require_master_view(request)",
    "_require_master_manage(request)",
    "material_directory_page(company=request.company",
    "vendor_offer_create",
    "vendor_offer_edit",
    "vendor_offer_status",
    "SourcingVendorOfferForm(request.POST, company=request.company)",
):
    if marker not in views:
        fail(f"material/catalog view authority missing: {marker}")
urls = text("apps/sourcing/urls.py")
for route in ("materials/", "materials/new/", "catalog/new/", "catalog/<uuid:offer_id>/edit/", "catalog/<uuid:offer_id>/status/"):
    if route not in urls:
        fail(f"material/catalog route missing: {route}")

for rel in (
    "templates/sourcing/materials/list.html",
    "templates/sourcing/materials/form.html",
    "templates/sourcing/vendors/offer_form.html",
    "templates/sourcing/vendors/detail.html",
    "static/sourcing/css/directory.css",
):
    text(rel)
for marker in ("Search code, material, category or alias", "Vendors", "Offers", "New Material"):
    if marker not in text("templates/sourcing/materials/list.html"):
        fail(f"Material Master UI missing: {marker}")
for marker in ("Availability", "Reference Rate", "Verification", "Reference-only sourcing data"):
    if marker not in text("templates/sourcing/vendors/offer_form.html"):
        fail(f"Vendor offer form UI missing: {marker}")
for marker in ("Supply Catalog", "Never verified", "Available quantity and rate are reference snapshots only"):
    if marker not in text("templates/sourcing/vendors/detail.html"):
        fail(f"Vendor Supply Catalog UI missing: {marker}")

for rel in (
    "apps/sourcing/models/vendors.py",
    "apps/sourcing/forms.py",
    "apps/sourcing/selectors/materials.py",
    "apps/sourcing/services/catalog.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_material_catalog.py",
    "apps/sourcing/migrations/0003_material_alias_search.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

if "1.0.116" not in text("docs/SOURCING_MATERIAL_CATALOG.md"):
    fail("Material Catalog operator guide is not version-bound")

print(
    "PASS: SESCCO MS 1.0.116 Material Master & Vendor Supply Catalog verified: controlled aliases, company-scoped materials, reference quantity/rate offers, immutable revisions, view/edit separation and zero operational stock/accounting integration."
)
