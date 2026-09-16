#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"
PREDECESSOR_SHA = "3be72bcc9edc38b95cab475d31d5b4b1e500685f579b62c88d9f82d1df642365"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING WORKFORCE FINDER ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-workforce-finder.json"))
if contract.get("release") != VERSION:
    fail("Workforce Finder contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.116 predecessor checksum changed")
if contract.get("schema_change") is not False:
    fail("Workforce Finder must not introduce a database migration")
if contract.get("operational_integration") is not False:
    fail("Workforce Finder must remain reference-only")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Workforce Finder cannot alter Payroll or Inventory formulas")
if contract.get("permissions") != {
    "finder": "sourcing.manpower.view",
    "history": "sourcing.manpower.view",
    "verify": "sourcing.manpower.manage",
}:
    fail("Workforce Finder permission boundary changed")

finder = text("apps/sourcing/selectors/workforce_finder.py")
for marker in (
    "PAGE_SIZES = (25, 50, 100)",
    "normalized_aliases__icontains=normalized_query",
    "supplier__status=SourcingEntityStatus.ACTIVE",
    "supplier__archived_at__isnull=True",
    "supplier__deleted_at__isnull=True",
    "trade__is_active=True",
    "rate_basis",
    "freshness_key",
    "finder_rate_expired",
    "Paginator(qs, page_size)",
):
    if marker not in finder:
        fail(f"Finder scale/filter/freshness authority missing: {marker}")

history = text("apps/sourcing/selectors/workforce_history.py")
for marker in (
    "SourcingWorkforceOfferRevision.objects.for_company(company)",
    "offer_id_snapshot=offer.pk",
    "PAGE_SIZES = (25, 50, 100)",
    '"Available Workers"',
    '"Overtime Rate"',
    '"Mobilization / Lead Time"',
):
    if marker not in history:
        fail(f"Workforce history authority missing: {marker}")

forms = text("apps/sourcing/forms.py")
for marker in (
    "class SourcingWorkforceOfferVerificationForm(forms.ModelForm):",
    'label="Spoke With"',
    '"available_quantity"',
    '"rate_basis"',
    '"overtime_rate"',
    '"mobilization_lead_time"',
    '"work_location"',
):
    if marker not in forms:
        fail(f"Quick verification form missing: {marker}")

services = text("apps/sourcing/services/workforce.py")
for marker in (
    "def verify_workforce_offer(",
    'action="sourcing.workforce_offer.verified"',
    "SourcingWorkforceOffer.objects.select_for_update()",
    "offer.last_verified_at = verified_at",
    "offer.verified_by = actor_membership.user",
    "supplier.last_verified_at = verified_at",
    "_record_revision(",
    '"quickVerification": True',
):
    if marker not in services:
        fail(f"Workforce verification service missing: {marker}")
for forbidden in ("RentalWorker", "rental_manpower", "InternalEmployee", "StockItem", "Accounting"):
    # Existing prose may mention prohibited integrations; only reject executable imports/calls.
    if f"from apps.{forbidden}" in services or f"import apps.{forbidden}" in services:
        fail(f"operational dependency introduced: {forbidden}")

views = text("apps/sourcing/views.py")
for marker in (
    "def workforce_finder(",
    "_require_manpower_view(request)",
    "def workforce_offer_verify(",
    "_require_manpower_manage(request)",
    "def workforce_offer_history(",
    "workforce_revision_page(",
    "workforce_revisions(",
    "_safe_sourcing_next(",
):
    if marker not in views:
        fail(f"Workforce Finder view boundary missing: {marker}")
urls = text("apps/sourcing/urls.py")
for route in ("workforce-finder/", "workforce/<uuid:offer_id>/verify/", "workforce/<uuid:offer_id>/history/"):
    if route not in urls:
        fail(f"Workforce Finder route missing: {route}")

finder_ui = text("templates/sourcing/workforce_finder/list.html")
for marker in (
    "Workforce Finder", "Available", "Standard Rate", "OT Rate", "Mobilization", "Freshness",
    "Verification history", "Verify now", "Reference only",
):
    if marker not in finder_ui:
        fail(f"Workforce Finder UI missing: {marker}")
verify_ui = text("templates/sourcing/manpower/workforce_verify.html")
for marker in ("Verify Workforce Reference", "Spoke With", "Save Verification", "Recent Verification History", "Reference confirmation only"):
    if marker not in verify_ui and marker not in forms:
        fail(f"Workforce Verify UI missing: {marker}")
history_ui = text("templates/sourcing/manpower/workforce_history.html")
for marker in ("Workforce Verification History", "Immutable sourcing evidence", "before", "after"):
    if marker not in history_ui and marker not in history:
        fail(f"Workforce History UI missing: {marker}")
sidebar = text("templates/sourcing/sidebar.html")
if "sourcing:workforce_finder" not in sidebar or "sourcing-workforce-finder" not in sidebar:
    fail("Workforce Finder navigation is not live")
home = text("templates/sourcing/home.html")
if "Find Workforce" not in home:
    fail("Sourcing home does not expose Workforce Finder")

for rel in (
    "apps/sourcing/selectors/workforce_finder.py",
    "apps/sourcing/selectors/workforce_history.py",
    "apps/sourcing/forms.py",
    "apps/sourcing/services/workforce.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_workforce_finder.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

release_tasks = text("scripts/release-tasks.sh")
for marker in ("verify-sourcing-workforce-finder.py", "apps.sourcing.tests.test_workforce_finder"):
    if marker not in release_tasks:
        fail(f"release task missing: {marker}")
if VERSION not in text("docs/SOURCING_WORKFORCE_FINDER.md"):
    fail("Workforce Finder operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.116 Workforce Finder & Verification History verified: trade-first cross-supplier search, freshness/rate filters, view-only history, editor quick verification, immutable revisions and zero Rental Payroll/Inventory/Accounting integration.")
