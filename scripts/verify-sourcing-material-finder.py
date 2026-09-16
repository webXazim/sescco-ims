#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
PREDECESSOR_SHA = "b96eb8585a20f52337871b8c04916976399cc3f59604a7ad33d5afe0745270ce"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING MATERIAL FINDER ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-material-finder.json"))
if contract.get("release") != VERSION:
    fail("Material Finder contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.102 predecessor checksum changed")
if contract.get("schema_change") is not False:
    fail("Material Finder must not claim a schema change")
if contract.get("operational_integration") is not False:
    fail("Material Finder must remain reference-only")
if contract.get("inventory_stock_effect") is not False or contract.get("accounting_posting") is not False:
    fail("Material Finder must not claim Inventory or Accounting effects")

freshness = text("apps/sourcing/freshness.py")
for marker in (
    "class SourcingFreshnessPolicy",
    "fresh_for_days: int = 7",
    "stale_after_days: int = 30",
    "FRESHNESS_NEEDS_VERIFICATION",
    "def sourcing_freshness_policy",
    "def freshness_key",
):
    if marker not in freshness:
        fail(f"freshness authority missing: {marker}")

selector = text("apps/sourcing/selectors/material_finder.py")
for marker in (
    "class MaterialFinderResult",
    "Paginator(qs, page_size)",
    "PAGE_SIZES = (25, 50, 100)",
    "material__normalized_aliases__icontains=normalized_query",
    "vendor__deleted_at__isnull=True",
    "vendor__archived_at__isnull=True",
    "vendor__status=SourcingEntityStatus.ACTIVE",
    "material__is_active=True",
    "last_verified_at__gte=fresh_cutoff",
    "last_verified_at__lt=stale_cutoff",
    "rate__gte=rate_min",
    "rate__lte=rate_max",
):
    if marker not in selector:
        fail(f"Material Finder selector authority missing: {marker}")
for forbidden in ("apps.inventory", "apps.rental_manpower", "apps.internal_payroll", "apps.accounting"):
    if forbidden in selector or forbidden in freshness:
        fail(f"Finder leaked operational dependency: {forbidden}")

views = text("apps/sourcing/views.py")
for marker in (
    "def material_finder(request: HttpRequest)",
    "_require_vendor_view(request)",
    "material_finder_page(company=request.company",
    'page_key="sourcing-material-finder"',
    "can_manage=membership_can_manage_vendor_sourcing",
):
    if marker not in views:
        fail(f"Material Finder view authority missing: {marker}")

urls = text("apps/sourcing/urls.py")
if 'path("material-finder/", views.material_finder, name="material_finder")' not in urls:
    fail("Material Finder route missing")

sidebar = text("templates/sourcing/sidebar.html")
if "{% url 'sourcing:material_finder' %}" not in sidebar or "sourcing-material-finder" not in sidebar:
    fail("Material Finder is not a permission-aware live navigation route")

template = text("templates/sourcing/material_finder/list.html")
for marker in (
    "Search material, code, alias, specification, brand, model or vendor",
    "Available Qty",
    "Reference Rate",
    "Freshness",
    "Never verified",
    "Reference only",
    "Edit reference",
):
    if marker not in template:
        fail(f"Material Finder UI missing: {marker}")
if "{% if can_manage %}" not in template:
    fail("Finder edit action is not guarded by Vendor manage authority")

release_tasks = text("scripts/release-tasks.sh")
if "verify-sourcing-material-finder.py" not in release_tasks:
    fail("Material Finder static gate is not release-required")
if "apps.sourcing.tests.test_material_finder" not in release_tasks:
    fail("Material Finder runtime regression is not release-required")

for rel in (
    "apps/sourcing/freshness.py",
    "apps/sourcing/selectors/material_finder.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_material_finder.py",
    "scripts/verify-sourcing-material-finder.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

if "1.0.115" not in text("docs/SOURCING_MATERIAL_FINDER.md"):
    fail("Material Finder operator guide is not version-bound")

print(
    "PASS: SESCCO MS 1.0.115 Material Finder verified: company-scoped Vendor offer search, controlled aliases, freshness policy, bounded server pagination, Vendor view/edit separation and zero operational Inventory/Payroll/Accounting integration."
)
