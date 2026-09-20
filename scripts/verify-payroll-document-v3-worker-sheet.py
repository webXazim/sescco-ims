#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-worker-sheet.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 WORKER SHEET ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("worker-sheet contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-worker-monthly-sheet-contract" or contract.get("upgrade_sequence") != "4/14":
    fail("unexpected worker-sheet upgrade identity")
if contract.get("state") != "worker_monthly_sheet_contract_internal_only":
    fail("worker monthly sheet must remain internal-only at this stage")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 4 must not add a migration or rewrite historical documents")
if contract.get("worker_sheet_contract_version") != "1.0":
    fail("worker monthly sheet contract version must be 1.0")

aggregator = text(contract["implementation"]["aggregator"])
for marker in (
    '"calendar_basis": "full_period"',
    '"outside_assignment_code": _OUTSIDE_ASSIGNMENT_CODE',
    '"overtime_basis": "monthly_worker_total"',
    '"daily_overtime_allowed": False',
    '"assignment_scope": "outside_assignment"',
    '"attendance_code": _OUTSIDE_ASSIGNMENT_CODE',
    '"assignment_scope": "assigned"',
    'worker["assignment_segments"] = _assignment_segments(days)',
    'worker["summary"]["overtime_hours"] = _hours(overtime_hours)',
    '"worker_sheet_contract": _worker_sheet_contract()',
):
    if marker not in aggregator:
        fail(f"worker monthly-sheet aggregator marker missing: {marker}")
if aggregator.count("supplier_code__iexact=normalized_supplier") != 2:
    fail("worker-sheet materialization must keep the two bounded supplier-filtered reads")
for forbidden in ('"rate":', '"rate_type":', "row.rate", "row.rate_type"):
    if forbidden in aggregator:
        fail(f"commercial data leaked into worker monthly sheet: {forbidden}")
calendar_start = aggregator.find("def _materialize_worker_calendar")
calendar_end = aggregator.find("\ndef build_supplier_timesheet_pack_snapshot", calendar_start)
if calendar_start < 0 or calendar_end < 0:
    fail("cannot locate worker calendar materializer")
calendar_block = aggregator[calendar_start:calendar_end]
if "objects." in calendar_block:
    fail("worker calendar materialization must remain query-free and in-memory")

schema = text(contract["implementation"]["schema_validator"])
for marker in (
    'SUPPLIER_TIMESHEET_WORKER_SHEET_CONTRACT_VERSION = "1.0"',
    'worker_sheet_contract.calendar_basis must be full_period.',
    'worker_sheet_contract.overtime_basis must be monthly_worker_total.',
    'outside-assignment rows cannot fabricate hours, trade or remarks.',
    'days must contain every calendar date in the pack period.',
    'assignment_segments must match contiguous assigned days and trade changes.',
    'summary.recorded_days must equal assigned_days for a locked source.',
    'summary.{key} must reconcile to the worker monthly-sheet summaries.',
):
    if marker not in schema:
        fail(f"worker monthly-sheet schema guard missing: {marker}")
if "raw_contract is None" not in schema or "Upgrade 3" not in schema:
    fail("Upgrade 3 internal v3 compatibility guard is missing")

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
    fail(f"Upgrade 4 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"worker-sheet regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_partial_assignment_materializes_complete_month_without_fabricating_attendance",
    "test_trade_change_creates_distinct_non_commercial_assignment_segments",
    "test_worker_sheet_contract_freezes_real_world_acknowledgement_roles",
    "test_schema_rejects_fabricated_outside_assignment_work_or_trade",
    "test_schema_rejects_missing_calendar_day_and_daily_ot_distribution",
}
if not required_methods.issubset(methods):
    fail(f"worker-sheet regression evidence incomplete: {sorted(required_methods - methods)}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-worker-sheet.py" not in text(rel):
        fail(f"worker-sheet contract is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack worker monthly-sheet contract: full-period calendar, explicit outside-assignment dates, "
    "locked attendance semantics, monthly-only OT, partial assignments, trade segments, remarks, acknowledgement roles, "
    "no commercial leakage and no API/UI activation."
)
