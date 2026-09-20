#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (ROOT / "apps/documents/services/documents.py").read_text(encoding="utf-8")
SCHEMA = (ROOT / "apps/documents/schema.py").read_text(encoding="utf-8")
SETTLEMENTS = (ROOT / "apps/rental_manpower/services/settlements.py").read_text(encoding="utf-8")
PRINT = (ROOT / "templates/documents/print.html").read_text(encoding="utf-8")
TYPE_FIRST = (ROOT / "apps/documents/services/type_first_generator.py").read_text(encoding="utf-8")
TESTS = (ROOT / "apps/documents/tests/test_v3_financial_document_reconciliation.py").read_text(encoding="utf-8")
RENTAL_TESTS = (ROOT / "apps/rental_manpower/tests/test_settlements.py").read_text(encoding="utf-8")
SCALE_SEED = (ROOT / "apps/core/management/payroll_seed_scale.py").read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 FINANCIAL RECONCILIATION ERROR: {message}")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


for needle, message in (
    ("assert_supplier_settlement_integrity(settlement)", "Settlement documents no longer re-check the approved settlement authority"),
    ('"authority": "approved_supplier_settlement"', "Settlement/invoice financial authority marker is missing"),
    ('"timesheet_pack_required": False', "Financial documents became dependent on a printable Timesheet Pack"),
    ('"match_basis": "approved_settlement_net"', "Supplier Invoice Received lost its settlement-net match basis"),
    ('"subtotal_variance": _money(subtotal - settlement.total_net)', "Supplier invoice subtotal variance is no longer explicit"),
    ('allocated_total != payment.amount', "Payment Advice no longer fails closed when allocations do not equal the paid amount"),
    ('verify_document_snapshot(invoice_doc)', "Payment Advice no longer verifies immutable Supplier Invoice records before reading them"),
    ('"source_timesheet_revision": settlement.source_timesheet_revision', "Payment allocations lost the source timesheet revision"),
    ('"settlement_net": _money(settlement.total_net)', "Payment allocations lost settlement-net reconciliation"),
):
    require(DOCUMENTS, needle, message)

for needle, message in (
    ('FINANCIAL_RECONCILIATION_CONTRACT_VERSION = "1.0"', "Financial reconciliation schema contract version is missing"),
    ('if contract is None:', "Historical v2 financial document compatibility guard is missing"),
    ('Financial authority must not depend on generating a Supplier Timesheet Pack.', "No-pack-dependency schema guard is missing"),
    ('Supplier invoice subtotal must exactly match the approved settlement net.', "Invoice settlement-net schema reconciliation is missing"),
    ('Payment Advice allocations must reconcile exactly to the paid amount.', "Payment allocation schema reconciliation is missing"),
):
    require(SCHEMA, needle, message)

# Approved-or-later document creation must use the frozen settlement snapshot as financial
# authority. A historical settlement cannot become unprintable merely because mutable/live
# operational source rows were normalized after approval. Calculated/Review transitions remain
# strict because the private workflow guard still recomputes the live source fingerprint.
settlement_tree = ast.parse(SETTLEMENTS)
settlement_lines = SETTLEMENTS.splitlines()
public_guard = next(
    (node for node in settlement_tree.body if isinstance(node, ast.FunctionDef) and node.name == "assert_supplier_settlement_integrity"),
    None,
)
if public_guard is None:
    fail("Approved settlement document integrity guard disappeared")
public_guard_source = "\n".join(settlement_lines[public_guard.lineno - 1 : public_guard.end_lineno])
for needle, message in (
    ("PAYABLE_SETTLEMENT_STATUSES", "Approved-or-later settlement documents are not using the frozen-authority branch"),
    ("settlement_snapshot_fingerprint(settlement)", "Approved settlement documents no longer verify the frozen snapshot"),
    ("_assert_settlement_integrity(settlement)", "Pre-approval settlement workflow no longer retains strict live-source integrity"),
    ("_normalize_legacy_scale_seed_integrity(settlement)", "Legacy scale-seed financial history no longer has its narrowly-scoped compatibility normalization"),
):
    require(public_guard_source, needle, message)
if "settlement_source_fingerprint(" in public_guard_source:
    fail("Approved document read-side guard recomputes mutable live source fingerprint")

for needle, message in (
    ('_SCALE_SEED_SETTLEMENT_PREFIX = "DEMO-SCALE-SET-"', "Scale-seed compatibility is not restricted to the synthetic settlement namespace"),
    ('_SCALE_SEED_REVIEW_MARKER = "DEMO SCALE SEED"', "Scale-seed compatibility lost its synthetic reviewer marker"),
    ('settlement.source_fingerprint == expected_source', "Scale-seed compatibility no longer requires the exact legacy source placeholder"),
    ('settlement.snapshot_fingerprint == expected_snapshot', "Scale-seed compatibility no longer requires the exact legacy snapshot placeholder"),
    ('_assert_scale_seed_snapshot_reconciles(', "Scale-seed placeholders can be canonicalized without reconciling frozen rows/source"),
    ('source_workers != seen_workers', "Scale-seed source/worker scope reconciliation is missing"),
):
    require(SETTLEMENTS, needle, message)

for needle, message in (
    ('source_fingerprint=_stable_sha256("rental", project_id, supplier_id, period_start)', "Scale seed no longer creates synthetic history with the legacy source placeholder"),
    ('snapshot_fingerprint=_stable_sha256("rental-snapshot", project_id, supplier_id, period_start, net)', "Scale seed no longer creates synthetic history with the legacy snapshot placeholder"),
    ('settlement.snapshot_fingerprint = _stable_sha256(', "Scale seed reconciliation no longer resets the synthetic snapshot placeholder when benchmark history expands"),
):
    require(SCALE_SEED, needle, message)

for needle, message in (
    ("Received from supplier", "Supplier Invoice Received direction is ambiguous in print output"),
    ("Matched to approved settlement net", "Supplier invoice match basis is not explicit in print output"),
    ("Locked Timesheet Revision", "Settlement/invoice print output lost locked timesheet revision evidence"),
    ("Not required for settlement authority", "Settlement print output no longer states the Timesheet Pack independence boundary"),
    ("Paid allocation reconciliation", "Payment Advice allocation reconciliation heading is missing"),
):
    require(PRINT, needle, message)

for needle, message in (
    ('"settlementRevision": source.revision', "Type-first review lost settlement revision"),
    ('"timesheetRevision": source.source_timesheet_revision', "Type-first review lost timesheet revision"),
    ('"timesheetPackRequired": False', "Type-first review became coupled to Supplier Timesheet Pack generation"),
    ('"allocatedTotal": _money(allocation_summary.get("allocated_total"))', "Payment review lost allocated-total reconciliation"),
):
    require(TYPE_FIRST, needle, message)

# Freeze the existing Rental settlement/payment authority for this document-only upgrade.
expected_function_hashes = {
    "_calculate_supplier_snapshot": "8bdf1a32b5b1b2410e0eeeca311a16fc492c5f2b67e08d9551381e8c0de79e6b",
    "settlement_source_fingerprint": "80589d0c89ad00df2ddb4786fb5c992e66048fda7a0042404eb23f767450ce1a",
    "settlement_snapshot_fingerprint": "7c996f65b6188610c9f2647b2c2966f8a2308a5e4ce6ff86c0929d2d73297c62",
    "_supplier_invoice_payable": "0dc3d4ec1bf2750f7bb4b3015d51de469ff88e033f81ba222c755d9af89874f6",
    "record_supplier_payment": "16fc1addd23c467b5b558506e3d000d64d6b4b6c8efa1da4788410a88d66f667",
}
tree = ast.parse(SETTLEMENTS)
source_lines = SETTLEMENTS.splitlines()
functions = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
for name, expected in expected_function_hashes.items():
    node = functions.get(name)
    if node is None:
        fail(f"Rental financial authority function disappeared: {name}")
    segment = "\n".join(source_lines[node.lineno - 1 : node.end_lineno]) + "\n"
    actual = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    if actual != expected:
        fail(f"Rental financial authority function changed during document reconciliation upgrade: {name}")

required_tests = (
    "test_settlement_statement_preserves_approved_totals_and_locked_timesheet_revision",
    "test_closed_settlement_statement_uses_frozen_snapshot_when_live_source_has_drifted",
    "test_calculated_settlement_still_requires_live_source_match_before_approval",
    "test_supplier_invoice_received_matches_approved_settlement_net_without_recalculating_it",
    "test_financial_schema_rejects_invoice_or_settlement_math_drift",
    "test_payment_advice_allocations_reconcile_exactly_to_paid_payment",
    "test_payment_advice_rejects_allocation_total_that_differs_from_paid_amount",
    "test_financial_print_language_keeps_invoice_direction_and_source_revisions_unambiguous",
)
for method in required_tests:
    require(TESTS, f"def {method}", f"Regression evidence missing: {method}")

required_rental_tests = (
    "test_legacy_scale_seed_placeholder_integrity_is_canonicalized_once_for_financial_documents",
    "test_legacy_scale_seed_normalization_fails_closed_when_frozen_line_totals_are_tampered",
    "test_non_seed_approved_settlement_with_snapshot_drift_still_fails_closed",
)
for method in required_rental_tests:
    require(RENTAL_TESTS, f"def {method}", f"Scale-seed settlement integrity regression evidence missing: {method}")

print("Verified Rental financial document reconciliation, including legacy scale-seed integrity normalization, without changing settlement/payment formulas.")
