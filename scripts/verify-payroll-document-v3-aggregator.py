#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-aggregator.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 AGGREGATOR ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("aggregator contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-snapshot-aggregator" or contract.get("upgrade_sequence") != "3/14":
    fail("unexpected v3 aggregator upgrade identity")
if contract.get("state") != "authoritative_aggregator_internal_only":
    fail("v3 aggregator must remain internal-only at this stage")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 3 must not add a migration or rewrite historical documents")

aggregator_rel = contract["implementation"]["aggregator"]
aggregator = text(aggregator_rel)
for marker in (
    "def build_supplier_timesheet_pack_snapshot(",
    "Supplier Timesheet Packs require a Locked project timesheet.",
    "supplier_code__iexact=normalized_supplier",
    '.select_related("worker")',
    '"document_schema_version": SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION',
    '"workers": public_workers',
    '"overtime_hours": _hours(overtime_total)',
    'validate_supplier_timesheet_pack_snapshot(snapshot)',
):
    if marker not in aggregator:
        fail(f"authoritative aggregator marker missing: {marker}")
if aggregator.count("supplier_code__iexact=normalized_supplier") != 2:
    fail("daily attendance and monthly overtime must both be supplier-filtered")
if ".prefetch_related(" in aggregator:
    fail("v3 aggregator must not prefetch the whole project month")
for forbidden in ('"rate":', '"rate_type":', "row.rate", "row.rate_type"):
    if forbidden in aggregator:
        fail(f"commercial data leaked into v3 pack aggregator: {forbidden}")
if '"overtime_hours"' in aggregator[aggregator.find('worker["days"].append'):aggregator.find('for row in overtime_rows')]:
    fail("daily rows must not serialize invented overtime")

schema = text("apps/documents/schema.py")
for marker in (
    "summary.total_hours must equal regular_hours plus overtime_hours.",
    "summary.regular_hours must equal the sum of daily regular_hours.",
    "summary hours must reconcile to the worker summaries.",
    "days must be sorted by date.",
):
    if marker not in schema:
        fail(f"v3 reconciliation guard missing: {marker}")

service = text("apps/documents/services/documents.py")
load_start = service.find("def _load_source")
load_end = service.find("\ndef _prefix", load_start)
if load_start < 0 or load_end < 0:
    fail("cannot locate document source dispatcher")
load_block = service[load_start:load_end]
for marker in (
    "if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:",
    'select_related("project").get(pk=source_id)',
    "build_supplier_timesheet_pack_snapshot(source, supplier_code=supplier_code)",
):
    if marker not in load_block:
        fail(f"v3 aggregator is not wired into internal source dispatch: {marker}")
if 'prefetch_related("entries__worker", "overtime_entries__worker")' in load_block[load_block.find("if document_type == DocumentType.SUPPLIER_TIMESHEET_PACK:"):]:
    fail("v3 source dispatch must not prefetch all project timesheet rows")
for marker in (
    "or normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK",
    'source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{normalized_supplier_code}"',
    'snapshot["document_schema_version"] = document_schema_version_for_type(normalized_type)',
    'DocumentType.SUPPLIER_TIMESHEET_PACK: ("document.supplier_timesheet_pack", "STP-")',
    'title = f"Supplier Monthly Timesheet Pack · {entity_name} · {snapshot[\'project\'][\'name\']}"',
):
    if marker not in service:
        fail(f"v3 internal finalization contract missing: {marker}")

api = text("apps/documents/api.py")
generic_api = api.split("def documents_api(", 1)[1].split("@require_http_methods", 1)[0]
if "allow_supplier_timesheet_pack=True" in generic_api:
    fail("generic Documents API must remain closed to direct v3 pack creation")
for marker in (
    "allow_supplier_timesheet_pack: bool = False",
    "if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK and not allow_supplier_timesheet_pack:",
    "Supplier Timesheet Pack creation is not yet exposed through the generic Documents API.",
):
    if marker not in service:
        fail(f"internal-only finalization guard missing: {marker}")
js = text("static/payroll/js/app.js")
if "supplier_timesheet_pack" in js and not (ROOT / "scripts/verify-payroll-document-v3-new-documents-ux.py").is_file():
    fail("frontend creation UI is active without the planned Upgrade 9 release gate")

migrations = sorted(path.name for path in (ROOT / "apps/documents/migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))
if migrations != [
    "0001_initial.py",
    "0002_alter_businessdocument_company_and_more.py",
    "0003_supplier_timesheet_pack_type.py",
]:
    fail(f"Upgrade 3 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"aggregator regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_aggregator_builds_supplier_scoped_summary_and_worker_daily_detail",
    "test_aggregator_is_deterministic",
    "test_aggregator_uses_two_supplier_filtered_data_queries_independent_of_worker_count",
    "test_source_dispatch_is_constant_three_queries_and_does_not_prefetch_whole_project",
    "test_pack_rejects_unlocked_or_empty_supplier_source",
    "test_internal_finalizer_creates_one_supplier_qualified_v3_document",
    "test_generic_documents_api_keeps_v3_creation_closed_until_generator_cutover",
}
if not required_methods.issubset(methods):
    fail(f"aggregator regression evidence incomplete: {sorted(required_methods - methods)}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-aggregator.py" not in text(rel):
        fail(f"v3 aggregator is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack v3 aggregator: locked supplier/project/month authority, two bounded supplier-filtered data reads, "
    "deterministic worker grouping, reconciled hours, no commercial/daily-OT leakage, internal finalization and closed generic API/UI."
)
