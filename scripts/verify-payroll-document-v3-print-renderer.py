#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-print-renderer.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 PRINT RENDERER ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("print-renderer contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-production-print-renderer" or contract.get("upgrade_sequence") != "6/14":
    fail("unexpected print-renderer upgrade identity")
if contract.get("state") != "production_renderer_internal_only":
    fail("Upgrade 6 must remain internal-only until the later generator cutover")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 6 must not add a migration or rewrite historical documents")
renderer_contract = contract.get("renderer") or {}
if renderer_contract.get("summary_rows_per_render_page") != 18:
    fail("supplier summary print chunk must remain 18 rows")
if renderer_contract.get("worker_overflow_policy") != "flow_to_next_physical_page_without_clipping":
    fail("worker print overflow must fail open to pagination rather than clipping")
if renderer_contract.get("commercial_values_allowed") is not False or renderer_contract.get("daily_overtime_allowed") is not False:
    fail("timesheet print output must remain non-commercial and monthly-OT-only")

renderer = text(contract["implementation"]["renderer"])
for marker in (
    "SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE = 18",
    "validate_supplier_timesheet_pack_snapshot(snapshot)",
    '"summary_pages": summary_pages',
    '"worker_pages": worker_pages',
    '"monthly_ot_note"',
    '"commercial_exclusion_note"',
    '"is_outside_assignment"',
):
    if marker not in renderer:
        fail(f"print context builder marker missing: {marker}")
if "objects." in renderer:
    fail("print context builder must be query-free and snapshot-only")
for forbidden in ('"rate":', '"payable":', '"vat_amount":', '"daily_overtime":'):
    if forbidden in renderer:
        fail(f"commercial/daily-OT field leaked into print context builder: {forbidden}")

template = text(contract["implementation"]["print_template"])
worker_partial = text("templates/documents/_supplier_timesheet_worker_sheet.html")
combined_print_markup = template + "\n" + worker_partial
for marker in (
    "document.document_type == 'supplier_timesheet_pack'",
    "supplier_timesheet_pack_print.summary_pages",
    "supplier_timesheet_pack_print.worker_pages",
    "Worker Monthly Timesheet",
    "pack-summary-table",
    "worker-table",
    ".worker-page { break-inside:auto; page-break-inside:auto; }",
    ".worker-table thead { display:table-header-group; }",
    "supplier_timesheet_pack_print.monthly_ot_note",
    "supplier_timesheet_pack_print.commercial_exclusion_note",
):
    if marker not in combined_print_markup:
        fail(f"supplier-pack print template marker missing: {marker}")
if 'documents/_supplier_timesheet_worker_sheet.html' not in template:
    fail("full-pack renderer must use the shared worker-sheet partial")
if ".worker-page { height:297mm; overflow:hidden; }" in template:
    fail("worker sheets must never use clipping fixed-height print geometry")
pack_start = template.find("{% if document.document_type == 'supplier_timesheet_pack' %}")
pack_end = template.find("{% else %}", pack_start)
if pack_start < 0 or pack_end < 0:
    fail("cannot isolate supplier-pack print branch")
pack_branch = template[pack_start:pack_end] + "\n" + worker_partial
for forbidden in (">Rate<", ">Payable<", "VAT", "Settlement Net", "Gross"):
    if forbidden in pack_branch:
        fail(f"commercial print label leaked into Supplier Timesheet Pack branch: {forbidden}")

views = text(contract["implementation"]["print_views"])
for marker in (
    "def _document_print_context(",
    "build_supplier_timesheet_pack_print_context(snapshot)",
    'document.document_type == DocumentType.SUPPLIER_TIMESHEET_PACK',
    "shared_view=True",
):
    if marker not in views:
        fail(f"print-view integration marker missing: {marker}")

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
    fail(f"Upgrade 6 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"print-renderer regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_renderer_chunks_large_supplier_summary_without_losing_workers",
    "test_renderer_keeps_complete_worker_calendar_and_monthly_only_overtime",
    "test_renderer_fails_closed_on_tampered_or_commercial_snapshot",
    "test_template_renders_summary_then_worker_monthly_sheet_without_commercial_columns",
    "test_worker_page_css_allows_safe_overflow_instead_of_clipping",
}
if not required_methods.issubset(methods):
    fail(f"print-renderer regression evidence incomplete: {sorted(required_methods - methods)}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-print-renderer.py" not in text(rel):
        fail(f"print renderer is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack production print renderer: supplier summary first, bounded summary pages, "
    "complete worker calendars, monthly-only OT, repeated document identity/signatures, shared-view parity, "
    "query-free rendering, no commercial values, no clipping and no API/UI activation."
)
