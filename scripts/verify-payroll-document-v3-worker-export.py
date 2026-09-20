#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-worker-export.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 WORKER EXPORT ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("worker-export contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-derived-worker-timesheet-export" or contract.get("upgrade_sequence") != "7/14":
    fail("unexpected worker-export upgrade identity")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 7 must not add a migration or rewrite historical documents")

export = contract.get("derived_export") or {}
for key in (
    "business_document_created",
    "database_queries_in_renderer",
    "commercial_values_allowed",
    "daily_overtime_allowed",
):
    if export.get(key) is not False:
        fail(f"derived worker export safety flag must remain false: {key}")
if export.get("source") != "immutable_parent_snapshot" or export.get("selection_key") != "worker_id":
    fail("derived worker export must select by worker_id from the immutable parent snapshot")
if export.get("full_parent_snapshot_validated_first") is not True:
    fail("the complete parent pack must be validated before worker extraction")

renderer = text(contract["implementation"]["renderer"])
for marker in (
    "class SupplierTimesheetPackWorkerNotFound",
    "def build_supplier_timesheet_pack_worker_print_context(",
    "validate_supplier_timesheet_pack_snapshot(snapshot)",
    '"derived_from_pack": True',
    '"worker": _worker_print_page(selected, period_label=period_label)',
):
    if marker not in renderer:
        fail(f"worker-export renderer marker missing: {marker}")
if "objects." in renderer:
    fail("worker export renderer must remain query-free")

views = text(contract["implementation"]["views"])
for marker in (
    "def _worker_timesheet_extract_context(",
    "def print_supplier_timesheet_worker(",
    "def delivery_pack_shared_worker_print(",
    "verify_document_snapshot(document)",
    "_share_documents(pack)",
    '"Cache-Control"] = "private, no-store"',
    '"X-Robots-Tag"] = "noindex, nofollow, noarchive"',
):
    if marker not in views:
        fail(f"worker-export view security marker missing: {marker}")

urls = text(contract["implementation"]["urls"])
for marker in (
    'name="print-supplier-timesheet-worker"',
    'name="delivery-pack-shared-worker-print"',
    "workers/<uuid:worker_id>/print/",
):
    if marker not in urls:
        fail(f"worker-export route marker missing: {marker}")

print_template = text(contract["implementation"]["print_template"])
partial = text(contract["implementation"]["worker_partial"])
for marker in (
    'worker_timesheet_extract',
    'documents/_supplier_timesheet_worker_sheet.html',
    'Print / Save PDF',
    'Full pack',
    'body.worker-extract .worker-page .pack-page-content',
):
    if marker not in print_template:
        fail(f"worker extract template marker missing: {marker}")
for marker in (
    "Derived from finalized supplier pack",
    "Worker Monthly Timesheet",
    "worker.days",
    "worker.summary.overtime_hours",
    "supplier_timesheet_pack_print.monthly_ot_note",
):
    if marker not in partial:
        fail(f"shared worker-sheet partial marker missing: {marker}")
for forbidden in (">Rate<", ">Payable<", "VAT", "Settlement Net", "Gross"):
    if forbidden in partial:
        fail(f"commercial label leaked into worker extract partial: {forbidden}")

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
    fail(f"Upgrade 7 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"worker-export regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_worker_extract_selects_one_worker_from_immutable_pack_without_mutation",
    "test_worker_extract_rejects_unknown_worker_and_tampered_snapshot",
    "test_internal_worker_print_route_renders_only_selected_worker_without_creating_document",
    "test_internal_worker_print_route_fails_closed_for_unknown_worker_and_non_pack_document",
    "test_supplier_share_worker_print_requires_pack_membership_and_uses_same_immutable_snapshot",
}
if not required_methods.issubset(methods):
    fail(f"worker-export regression evidence incomplete: {sorted(required_methods - methods)}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-worker-export.py" not in text(rel):
        fail(f"derived worker export is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack derived worker export: one immutable parent document, exact worker-id selection, "
    "same worker-sheet renderer, internal and supplier-share routes, snapshot integrity and pack-membership enforcement, "
    "private no-store output, monthly-only OT, no commercial values, no migration and no generic API/UI activation."
)
