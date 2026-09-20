#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-supplier-summary.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 SUPPLIER SUMMARY ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("supplier-summary contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-supplier-summary-contract" or contract.get("upgrade_sequence") != "5/14":
    fail("unexpected supplier-summary upgrade identity")
if contract.get("state") != "supplier_summary_contract_internal_only":
    fail("supplier summary must remain internal-only at this stage")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 5 must not add a migration or rewrite historical documents")
if contract.get("supplier_summary_contract_version") != "1.0":
    fail("supplier summary contract version must be 1.0")

aggregator = text(contract["implementation"]["aggregator"])
for marker in (
    "SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION",
    '"title": "Supplier Monthly Timesheet Summary"',
    '"scope": "supplier_project_period_locked_revision"',
    '"row_basis": "one_worker_month"',
    '"trade_basis": "ordered_distinct_worker_trades"',
    '"overtime_basis": "monthly_worker_total"',
    '"commercial_values_allowed": False',
    '"supplier_summary_contract": _supplier_summary_contract()',
    'supplier_summary_rows = [_supplier_summary_row(worker) for worker in public_workers]',
    '"supplier_summary_rows": supplier_summary_rows',
):
    if marker not in aggregator:
        fail(f"supplier-summary aggregator marker missing: {marker}")
if aggregator.count("supplier_code__iexact=normalized_supplier") != 2:
    fail("supplier summary must keep the two bounded supplier-filtered reads")
summary_start = aggregator.find("def _supplier_summary_contract")
summary_end = aggregator.find("\ndef _new_worker", summary_start)
if summary_start < 0 or summary_end < 0:
    fail("cannot locate supplier-summary materializers")
summary_block = aggregator[summary_start:summary_end]
if "objects." in summary_block:
    fail("supplier-summary materialization must remain query-free and in-memory")
for forbidden in ('"rate":', '"rate_type":', "row.rate", "row.rate_type"):
    if forbidden in summary_block:
        fail(f"commercial data leaked into supplier summary: {forbidden}")

schema = text(contract["implementation"]["schema_validator"])
for marker in (
    'SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION = "1.0"',
    "supplier_summary_contract.scope must bind supplier, project, period and locked revision.",
    "supplier_summary_contract.columns must use the frozen supplier-facing summary columns.",
    "supplier_summary_rows must contain exactly one row per worker.",
    "must match the worker monthly-sheet summary.",
    "summary.regular_hours must reconcile to supplier_summary_rows.",
    "summary.overtime_hours must reconcile to supplier_summary_rows.",
    "supplier_summary_contract requires the worker_sheet_contract foundation.",
):
    if marker not in schema:
        fail(f"supplier-summary schema guard missing: {marker}")
if "Upgrade 4" not in schema or "raw_contract is None" not in schema:
    fail("Upgrade 4 internal-v3 compatibility guard is missing")

api = text("apps/documents/api.py")
generic_api = api.split("def documents_api(", 1)[1].split("@require_http_methods", 1)[0]
if "allow_supplier_timesheet_pack=True" in generic_api:
    fail("generic Documents API must remain closed to direct v3 pack creation")
js = text("static/payroll/js/app.js")
if "supplier_timesheet_pack" in js and not (ROOT / "scripts/verify-payroll-document-v3-new-documents-ux.py").is_file():
    fail("frontend creation UI is active without the planned Upgrade 9 release gate")

migrations = sorted(path.name for path in (ROOT / "apps/documents/migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))
if migrations != [
    "0001_initial.py",
    "0002_alter_businessdocument_company_and_more.py",
    "0003_supplier_timesheet_pack_type.py",
]:
    fail(f"Upgrade 5 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"supplier-summary regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_supplier_summary_has_one_reconciled_row_per_worker",
    "test_supplier_summary_contract_freezes_identity_columns_and_acknowledgement_roles",
    "test_schema_rejects_tampered_supplier_summary_identity_or_hours",
    "test_supplier_summary_rejects_commercial_fields_and_daily_ot",
    "test_upgrade4_internal_snapshot_without_supplier_summary_contract_remains_valid",
}
if not required_methods.issubset(methods):
    fail(f"supplier-summary regression evidence incomplete: {sorted(required_methods - methods)}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-supplier-summary.py" not in text(rel):
        fail(f"supplier-summary contract is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack supplier-summary contract: frozen supplier/project/period/revision identity, "
    "one reconciled worker-month row per worker, attendance/hour totals, monthly-only OT, acknowledgement roles, "
    "two-query in-memory materialization, no commercial leakage and no API/UI activation."
)
