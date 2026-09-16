#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.113"
PREDECESSOR_SHA = "490c83bdcaab2f4586b973ca5ac78f11051df2429babd5a6c9683c3610516214"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING VENDOR VERIFICATION ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-vendor-verification.json"))
if contract.get("release") != VERSION:
    fail("Vendor verification contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.103 predecessor checksum changed")
if contract.get("schema_change") is not False:
    fail("Vendor verification must not claim a schema change")
if contract.get("operational_integration") is not False:
    fail("Vendor verification must remain reference-only")
for key in ("inventory_stock_effect", "accounting_posting", "payroll_effect"):
    if contract.get(key) is not False:
        fail(f"Vendor verification isolation changed: {key}")

forms = text("apps/sourcing/forms.py")
for marker in (
    "class SourcingVendorOfferVerificationForm",
    'label="Spoke With"',
    '"available_quantity"',
    '"rate_valid_until"',
    '"verification_note"',
):
    if marker not in forms:
        fail(f"Quick verification form missing: {marker}")

service = text("apps/sourcing/services/catalog.py")
for marker in (
    "def verify_vendor_offer(",
    "SourcingVendorOffer.objects.select_for_update()",
    "offer.last_verified_at = verified_at",
    "offer.verified_by = actor_membership.user",
    "_record_offer_revision(",
    'action="sourcing.vendor_offer.verified"',
    '"quickVerification": True',
):
    if marker not in service:
        fail(f"Verification service authority missing: {marker}")
for forbidden in ("apps.inventory", "apps.rental_manpower", "apps.internal_payroll", "apps.accounting"):
    if forbidden in service:
        fail(f"Verification service leaked operational dependency: {forbidden}")

selector = text("apps/sourcing/selectors/catalog.py")
for marker in (
    "def offer_revision_page(",
    "Paginator(queryset, size)",
    "PAGE_SIZES = (25, 50, 100)",
    "def _revision_changes",
):
    if marker not in selector:
        fail(f"Verification history selector missing: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "def vendor_offer_verify(request: HttpRequest, vendor_id, offer_id)",
    "_require_vendor_manage(request)",
    "def vendor_offer_history(request: HttpRequest, vendor_id, offer_id)",
    "_require_vendor_view(request)",
    "verify_vendor_offer(",
    "offer_revision_page(",
):
    if marker not in views:
        fail(f"Verification view authority missing: {marker}")

urls = text("apps/sourcing/urls.py")
for marker in (
    'name="vendor_offer_verify"',
    'name="vendor_offer_history"',
):
    if marker not in urls:
        fail(f"Verification route missing: {marker}")

verify_template = text("templates/sourcing/vendors/offer_verify.html")
history_template = text("templates/sourcing/vendors/offer_history.html")
finder_template = text("templates/sourcing/material_finder/list.html")
detail_template = text("templates/sourcing/vendors/detail.html")
for marker in ("Save Verification", "form.contact_name", "Recent Verification History", "Reference-only verification"):
    if marker not in verify_template:
        fail(f"Verification UX missing: {marker}")
for marker in ("Verification History", "Immutable sourcing evidence", "before", "after"):
    if marker not in history_template:
        fail(f"History UX missing: {marker}")
if "Verify now" not in finder_template or "vendor_offer_history" not in finder_template:
    fail("Material Finder does not expose verification/history workflow")
if "Verify now" not in detail_template or "Verification history" not in detail_template:
    fail("Vendor Supply Catalog does not expose verification/history workflow")

release_tasks = text("scripts/release-tasks.sh")
if "verify-sourcing-vendor-verification.py" not in release_tasks:
    fail("Vendor verification static gate is not release-required")
if "apps.sourcing.tests.test_vendor_verification" not in release_tasks:
    fail("Vendor verification runtime regression is not release-required")

for rel in (
    "apps/sourcing/forms.py",
    "apps/sourcing/selectors/catalog.py",
    "apps/sourcing/services/catalog.py",
    "apps/sourcing/views.py",
    "apps/sourcing/urls.py",
    "apps/sourcing/tests/test_vendor_verification.py",
    "scripts/verify-sourcing-vendor-verification.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

if "1.0.113" not in text("docs/SOURCING_VENDOR_VERIFICATION.md"):
    fail("Vendor verification operator guide is not version-bound")

print(
    "PASS: SESCCO MS 1.0.113 Vendor Verification & History UX verified: manage-only quick confirmation, view-only immutable history, before/after revision evidence, bounded history pagination, Material Finder freshness renewal and zero Inventory/Payroll/Accounting integration."
)
