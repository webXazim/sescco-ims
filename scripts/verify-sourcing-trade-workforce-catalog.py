#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
PREDECESSOR_SHA = "ab85b97e9fa9f60467799c6c158e950f0d8fb12d0ddb0a6eb493e69e4ab75e0f"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING TRADE/WORKFORCE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-trade-workforce-catalog.json"))
if contract.get("release") != VERSION:
    fail("trade/workforce contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.117 predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("1.0.117 must declare the Trade alias-search schema change")
if contract.get("operational_integration") is not False:
    fail("Workforce Catalog must remain reference-only")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Trade/Workforce catalog cannot change Payroll or Inventory formulas")
if contract.get("rate_bases") != ["hour", "day", "month"]:
    fail("rate basis authority changed")

models = text("apps/sourcing/models/manpower.py")
for marker in (
    "class SourcingTrade(CompanyOwnedModel):",
    "normalized_aliases = models.TextField(blank=True, editable=False)",
    "Trade name/alias conflicts with",
    "class SourcingWorkforceOffer(SourcingRateMixin, CompanyOwnedModel):",
    "available_quantity = models.PositiveIntegerField(null=True, blank=True)",
    "rate_basis = models.CharField",
    "overtime_rate = models.DecimalField",
    "mobilization_lead_time = models.CharField",
    "work_location = models.CharField",
    "last_verified_at = models.DateTimeField",
    "class SourcingWorkforceOfferRevision(CompanyOwnedModel):",
    "Sourcing workforce revisions are immutable.",
):
    if marker not in models:
        fail(f"Trade/Workforce model authority missing: {marker}")
for forbidden in ("inventory.", "rental_manpower.", "internal_payroll.", "accounting."):
    if f'to="{forbidden}' in models:
        fail(f"operational foreign key introduced in Sourcing manpower models: {forbidden}")

migration = text("apps/sourcing/migrations/0005_trade_alias_search.py")
for marker in (
    '("sourcing", "0004_manpower_supplier_contacts")',
    'model_name="sourcingtrade"',
    'name="normalized_aliases"',
    "populate_normalized_aliases",
):
    if marker not in migration:
        fail(f"Trade alias migration missing: {marker}")
for forbidden in ('to="inventory.', 'to="rental_manpower.', 'to="internal_payroll.'):
    if forbidden in migration:
        fail(f"Trade alias migration contains operational FK: {forbidden}")

forms = text("apps/sourcing/forms.py")
for marker in (
    "class SourcingTradeForm(forms.ModelForm):",
    "class SourcingWorkforceOfferForm(forms.ModelForm):",
    'label="Verified now"',
    'label="Spoke With"',
    '"rate_basis"',
    '"overtime_rate"',
    '"mobilization_lead_time"',
    '"work_location"',
):
    if marker not in forms:
        fail(f"Trade/Workforce form authority missing: {marker}")

trades = text("apps/sourcing/selectors/trades.py")
for marker in (
    "PAGE_SIZES = (25, 50, 100)",
    "Paginator(qs, page_size)",
    "normalized_aliases__icontains=normalized_query",
    "trade_directory_scale_annotations",
):
    if marker not in trades:
        fail(f"Trade directory scale/search authority missing: {marker}")
workforce_selector = text("apps/sourcing/selectors/workforce.py")
for marker in ("SourcingWorkforceOffer.objects.for_company(company)", '.filter(supplier=supplier)', '.select_related("trade", "verified_by")'):
    if marker not in workforce_selector:
        fail(f"Workforce catalog selector missing: {marker}")

services = text("apps/sourcing/services/workforce.py")
for action in contract.get("audit_actions", []):
    if f'"{action}"' not in services:
        fail(f"Trade/Workforce audit action missing: {action}")
for marker in (
    "SourcingWorkforceOfferRevision.objects.create",
    "supplier.last_verified_at = offer.last_verified_at",
    "verified_by = actor_membership.user",
    "Restore the archived Manpower Supplier before changing its Workforce Catalog.",
    "Inactive Sourcing Trades cannot be added",
    "select_for_update()",
    "def delete_trade(",
    "def delete_workforce_offer(",
    'action="sourcing.trade.deleted"',
    'action="sourcing.workforce_offer.deleted"',
    "retainedVerificationRevisions",
):
    if marker not in services:
        fail(f"Workforce service safety/evidence missing: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "def trade_list(", "def trade_create(", "def trade_edit(", "def trade_status(", "def trade_delete(",
    "def workforce_offer_create(", "def workforce_offer_edit(", "def workforce_offer_status(", "def workforce_offer_delete(",
    "_require_master_view(request)", "_require_master_manage(request)",
    "_require_manpower_manage(request)",
    "workforce_catalog_page(",
):
    if marker not in views:
        fail(f"Trade/Workforce view authority missing: {marker}")
urls = text("apps/sourcing/urls.py")
for route in ("trades/", "trades/new/", "trades/<uuid:trade_id>/delete/", "workforce/new/", "workforce/<uuid:offer_id>/edit/", "workforce/<uuid:offer_id>/status/", "workforce/<uuid:offer_id>/delete/"):
    if route not in urls:
        fail(f"Trade/Workforce route missing: {route}")

for rel in (
    "templates/sourcing/trades/list.html",
    "templates/sourcing/trades/form.html",
    "templates/sourcing/manpower/workforce_form.html",
    "templates/sourcing/manpower/detail.html",
    "templates/sourcing/sidebar.html",
):
    text(rel)
trade_list = text("templates/sourcing/trades/list.html")
for marker in ("Search code, trade, category or alias", "New Trade", "Suppliers", "Capabilities", "Delete permanently"):
    if marker not in trade_list:
        fail(f"Trade master UI missing: {marker}")
manpower_detail = text("templates/sourcing/manpower/detail.html")
for marker in ("+ Add Worker Type", "Available", "OT Rate", "Mobilization", "Rental Payroll workers"):
    if marker not in manpower_detail:
        fail(f"Workforce Catalog profile UI missing: {marker}")
workforce_form = text("templates/sourcing/manpower/workforce_form.html")
for marker in ("Reference-only manpower data", "Rate Basis", "Overtime Rate", "Mobilization / Lead Time", "Verified now"):
    if marker not in workforce_form and marker not in forms:
        fail(f"Workforce Catalog form missing: {marker}")
sidebar = text("templates/sourcing/sidebar.html")
if "sourcing:trade_list" not in sidebar or "Worker Types / Trades" not in sidebar:
    fail("Trade master navigation is not live")

retention = json.loads(text("merge/lifecycle-retention-contract.json"))
expected_modes = {
    "sourcing.SourcingTrade": "reference_master_inactive_hard_delete",
    "sourcing.SourcingWorkforceOffer": "reference_offer_inactive_hard_delete",
    "sourcing.SourcingWorkforceOfferRevision": "immutable_reference_history",
}
for model, mode in expected_modes.items():
    if retention.get("models", {}).get(model, {}).get("mode") != mode:
        fail(f"retention classification changed for {model}")

for rel in (
    "apps/sourcing/models/manpower.py",
    "apps/sourcing/forms.py",
    "apps/sourcing/selectors/trades.py",
    "apps/sourcing/selectors/workforce.py",
    "apps/sourcing/services/workforce.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_trade_workforce_catalog.py",
    "apps/sourcing/migrations/0005_trade_alias_search.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

release_tasks = text("scripts/release-tasks.sh")
for marker in ("verify-sourcing-trade-workforce-catalog.py", "apps.sourcing.tests.test_trade_workforce_catalog"):
    if marker not in release_tasks:
        fail(f"release task missing: {marker}")
if "1.0.117" not in text("docs/SOURCING_TRADE_WORKFORCE_CATALOG.md"):
    fail("Trade/Workforce operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.117 Worker Trade Master & Workforce Catalog verified: controlled aliases, company-scoped trade master, reference workforce quantity/rates, immutable revisions, view/edit separation and zero Rental Payroll/Inventory/Accounting integration.")
