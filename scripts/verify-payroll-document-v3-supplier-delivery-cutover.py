#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = (ROOT / "apps/documents/delivery.py").read_text(encoding="utf-8")
API = (ROOT / "apps/documents/api.py").read_text(encoding="utf-8")
VIEWS = (ROOT / "apps/documents/views.py").read_text(encoding="utf-8")
SHARE = (ROOT / "templates/documents/delivery_share.html").read_text(encoding="utf-8")
PACK = (ROOT / "templates/documents/delivery_pack.html").read_text(encoding="utf-8")
FRONTEND = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
TESTS = (ROOT / "apps/documents/tests/test_v3_supplier_delivery_cutover.py").read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 SUPPLIER DELIVERY CUTOVER ERROR: {message}")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


for needle, message in (
    ('SUPPLIER_DELIVERY_CONTRACT_VERSION = "2.0"', "Supplier delivery v2 contract marker is missing"),
    ('SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE = "receipt_only"', "Receipt-only acknowledgement boundary is missing"),
    ('SUPPLIER_DELIVERY_PRIMARY_TYPE = "supplier_timesheet_pack"', "Supplier Timesheet Pack is no longer the primary delivery type"),
    ('def prefer_v3_supplier_timesheets', "Legacy/v3 timesheet de-duplication policy is missing"),
    ('def supplier_delivery_filename', "Stable supplier delivery filename policy is missing"),
    ('"supplier_timesheet_pack": "Supplier Monthly Timesheet Pack"', "Supplier Timesheet Pack delivery label is missing"),
):
    require(DELIVERY, needle, message)

for needle, message in (
    ('DocumentType.SUPPLIER_TIMESHEET_PACK', "Delivery center no longer includes v3 Supplier Timesheet Packs"),
    ('document_manifest = [supplier_delivery_manifest_entry(row) for row in rows]', "Issued delivery pack no longer freezes its document manifest"),
    ('"primary_document_ids": primary_document_ids', "Issued delivery pack no longer freezes primary document identity"),
    ('"acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE', "Issued delivery pack lost receipt-only acknowledgement scope"),
    ('default_channel = "email" if (supplier and supplier.email)', "Supplier-master delivery channel default is missing"),
    ('"recommendedDocumentIds": sorted(recommended_ids)', "Primary timesheet recommendation is missing from delivery options"),
    ('Acknowledgement confirms receipt only', "Supplier email no longer explains receipt-only acknowledgement"),
):
    require(API, needle, message)

# Supplier Invoice Received is inbound to SESCCO and must not become an outbound supplier document.
role_block = DELIVERY.split("def supplier_delivery_document_role", 1)[1].split("def supplier_delivery_document_label", 1)[0]
if "supplier_invoice" in role_block:
    fail("Supplier Invoice Received was incorrectly added to outbound supplier delivery roles")

for needle, message in (
    ('"document_entries": _delivery_document_entries(pack, documents)', "Supplier share/print no longer uses the frozen delivery manifest"),
    ('"X-Content-Type-Options"] = "nosniff"', "Supplier share security headers lost nosniff"),
    ('"acknowledgement_scope": SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE', "Supplier acknowledgement events lost receipt-only scope"),
    ('return _private_print_response(response)', "Shared document print no longer uses private no-store response protection"),
):
    require(VIEWS, needle, message)

for needle, message in (
    ("Primary timesheet", "Supplier portal does not identify the authoritative timesheet"),
    ("Open Full Pack", "Supplier portal lost the full Timesheet Pack action"),
    ("Acknowledgement confirms that this supplier document pack was received and opened", "Supplier portal acknowledgement wording is missing"),
    ("does not approve, alter, or replace", "Supplier portal no longer protects approval authority semantics"),
):
    require(SHARE, needle, message)

require(PACK, "Receipt only", "Printed delivery cover lost receipt-only acknowledgement scope")
require(PACK, "Primary supplier timesheet", "Printed delivery cover lost primary timesheet identification")
require(FRONTEND, "supplier_timesheet_pack", "Frontend cannot issue the new Supplier Timesheet Pack")
require(FRONTEND, "isPrimaryDelivery", "Frontend lost primary-timesheet delivery emphasis")
require(FRONTEND, "recommended", "Bulk supplier delivery no longer preselects recommended timesheets")

required_tests = (
    "test_delivery_policy_treats_v3_pack_as_primary_and_hides_exact_legacy_replacement",
    "test_delivery_options_promotes_v3_pack_and_uses_supplier_master_defaults",
    "test_delivery_center_includes_v3_pack_and_suppresses_legacy_equivalent",
    "test_issued_pack_freezes_manifest_primary_identity_and_receipt_scope",
    "test_supplier_share_renders_primary_full_pack_filename_and_receipt_only_language",
    "test_supplier_acknowledgement_is_receipt_only_and_retry_safe",
    "test_email_dispatch_names_primary_timesheet_and_explains_receipt_only_acknowledgement",
)
for method in required_tests:
    require(TESTS, f"def {method}", f"Regression evidence missing: {method}")

print("Verified Supplier Timesheet Pack v3 supplier delivery cutover, receipt-only acknowledgement and legacy compatibility.")
