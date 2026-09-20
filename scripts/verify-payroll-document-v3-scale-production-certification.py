#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "merge/payroll-document-v3-scale-production-certification.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
AGGREGATOR = (ROOT / "apps/documents/services/supplier_timesheet_pack.py").read_text(encoding="utf-8")
FINALIZER = (ROOT / "apps/documents/services/documents.py").read_text(encoding="utf-8")
PRINTING = (ROOT / "apps/documents/printing.py").read_text(encoding="utf-8")
COMMAND = (ROOT / "apps/documents/management/commands/supplier_timesheet_pack_scale_report.py").read_text(encoding="utf-8")
TESTS = (ROOT / "apps/documents/tests/test_v3_scale_production_certification.py").read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 SCALE CERTIFICATION ERROR: {message}")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


if CONTRACT.get("release") != "1.0.117" or CONTRACT.get("upgrade_sequence") != "13/14":
    fail("scale certification contract release/sequence is not frozen at Upgrade 13/14")
if CONTRACT.get("certified_worker_volume") != 250:
    fail("250-worker production certification target changed")
if CONTRACT.get("certified_worker_volumes") != [1, 50, 250]:
    fail("1/50/250 worker scale certification matrix changed")
if (CONTRACT.get("query_budgets") or {}).get("snapshot_aggregator") != 2:
    fail("Supplier Timesheet Pack aggregator query budget changed")
if (CONTRACT.get("query_budgets") or {}).get("full_print_context") != 0:
    fail("full-pack rendering must remain query-free")
if (CONTRACT.get("snapshot_budget") or {}).get("max_mib_at_250_workers") != 8:
    fail("250-worker immutable snapshot certification budget changed")

for needle, message in (
    ("entries = list(", "aggregator no longer materializes one bounded supplier entry query"),
    ("overtime_rows = list(", "aggregator no longer materializes one bounded supplier overtime query"),
    ("validate_supplier_timesheet_pack_snapshot(snapshot)", "aggregator lost immutable snapshot validation"),
):
    require(AGGREGATOR, needle, message)

require(
    FINALIZER,
    '@transaction.atomic\ndef finalize_business_document(',
    "document finalization is not transactionally atomic around the Supplier Timesheet Pack source lock",
)
require(
    FINALIZER,
    'source.__class__._default_manager.select_for_update().only("pk").get(pk=source.pk)',
    "Supplier Timesheet Pack finalization lost source-row serialization for concurrent retries",
)
require(
    FINALIZER,
    "if existing:\n        if verify_document_snapshot(existing):\n            return existing",
    "finalization no longer returns the existing integrity-verified document on retry",
)

for needle, message in (
    ("SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE = 18", "summary pagination contract changed"),
    ("validate_supplier_timesheet_pack_snapshot(snapshot)", "print builder lost snapshot validation"),
    ('"worker_page_count": len(worker_pages)', "print builder lost worker-page reconciliation metadata"),
):
    require(PRINTING, needle, message)

for needle, message in (
    ("DEFAULT_MAX_AGGREGATE_QUERIES = 2", "scale command aggregator query budget changed"),
    ("DEFAULT_MAX_PRINT_QUERIES = 0", "scale command print query budget changed"),
    ("DEFAULT_MAX_SNAPSHOT_MIB = 8.0", "scale command snapshot budget changed"),
    ("CaptureQueriesContext(connection)", "scale command no longer measures real SQL query counts"),
    ("build_supplier_timesheet_pack_snapshot", "scale command no longer exercises the production aggregator"),
    ("build_supplier_timesheet_pack_print_context", "scale command no longer exercises full-pack rendering"),
    ("build_supplier_timesheet_pack_worker_print_context", "scale command no longer exercises derived worker rendering"),
    ('parser.add_argument("--min-workers"', "scale command lost minimum-volume certification control"),
    ('parser.add_argument("--fail-on-limits"', "scale command lost fail-closed certification mode"),
):
    require(COMMAND, needle, message)

required_tests = (
    "test_1_and_50_worker_sources_keep_the_same_two_query_budget",
    "test_250_worker_pack_uses_two_data_queries_and_stays_within_snapshot_budget",
    "test_250_worker_full_print_and_worker_extract_are_query_free_and_reconcile",
    "test_finalization_is_retry_safe_and_keeps_one_immutable_pack",
    "test_scale_report_command_certifies_real_250_worker_locked_source",
    "test_concurrent_pack_finalization_returns_one_document_without_integrity_error",
)
for method in required_tests:
    require(TESTS, f"def {method}", f"Regression evidence missing: {method}")

require(TESTS, "CERTIFIED_WORKERS = 250", "runtime scale fixture no longer certifies 250 workers")
require(TESTS, "CERTIFIED_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024", "runtime snapshot budget evidence changed")
require(TESTS, 'if connection.vendor != "postgresql":', "concurrent finalization test is not explicitly PostgreSQL-scoped")

print("Verified Supplier Timesheet Pack v3 250-worker scale, query budgets, query-free rendering and concurrent finalization hardening.")
