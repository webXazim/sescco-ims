#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"RENTAL ADJUSTMENT PAGE SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

version = text("VERSION").strip()
if version != "1.0.116":
    fail(f"VERSION must be 1.0.116, found {version!r}")
contract = json.loads(text("merge/payroll-rental-adjustment-page-scale.json"))
if contract.get("release") != version:
    fail("page-scale contract release does not match VERSION")
if set(contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("Worker Adjustments must stay bounded to 25/50/100 rows")
if contract.get("settlement_context_on_page_load") is not False or contract.get("settlement_context_on_mutation") is not False:
    fail("Worker Adjustments must remain independent of the settlement mega-context")

api = text("apps/rental_manpower/api.py")
selectors = text("apps/rental_manpower/selectors/settlements.py")
js = text("static/payroll/js/app.js")
tests = text("apps/rental_manpower/tests/test_api.py")
for rel, source in (("apps/rental_manpower/api.py", api), ("apps/rental_manpower/selectors/settlements.py", selectors), ("apps/rental_manpower/tests/test_api.py", tests)):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "def rental_adjustment_page_context(",
    "Paginator(queryset, size)",
    "'surface': 'rental_adjustments_page'",
    "_rental_adjustment_period_summary",
    "project_name__icontains=project_query",
    "supplier_name__icontains=supplier_query",
    ".select_related('project', 'submitted_by', 'approved_by')",
):
    if needle not in selectors:
        fail(f"bounded server page protection missing: {needle}")

start = api.find("def rental_adjustments_api(request: HttpRequest)")
end = api.find("def rental_adjustment_detail_api", start)
if start < 0 or end < 0:
    fail("could not isolate rental_adjustments_api")
get_post = api[start:end]
if "rental_adjustment_page_context(" not in get_post:
    fail("GET Worker Adjustments does not use the bounded page selector")
if "rental_settlement_context(" in get_post:
    fail("GET/create Worker Adjustments regressed to the settlement mega-context")

for function_name in ("rental_adjustment_detail_api", "rental_adjustment_workflow_api"):
    start = api.find(f"def {function_name}")
    next_marker = api.find("\n@require_http_methods", start + 5)
    body = api[start:next_marker if next_marker > start else len(api)]
    if "rental_settlement_context(" in body:
        fail(f"{function_name} regressed to full settlement-context mutations")

for needle in (
    "function rentalAdjustmentRequest(period = state.period)",
    "function loadRentalAdjustmentPage(period = state.period",
    "cancelRentalAdjustmentRequest()",
    "rental_adjustments_page",
    "project_search:state.adjustmentProjectSearch",
    "supplier_search:state.adjustmentSupplierSearch",
    "adjustmentProjectSearch",
    "adjustmentSupplierSearch",
    "await refreshRentalAdjustmentAuthority",
):
    if needle not in js:
        fail(f"bounded browser page protection missing: {needle}")

adjustment_start = js.find("  function adjustmentRegisterTemplate() {")
adjustment_end = js.find("  function adjustmentBalancesTemplate()", adjustment_start)
if adjustment_start < 0 or adjustment_end < 0:
    fail("could not isolate adjustment register renderer")
register = js[adjustment_start:adjustment_end]
if "state.projects.filter" in register or "state.suppliers.filter" in register:
    fail("Worker Adjustments still renders full Project/Supplier masters into filter options")

page_start = js.find("  function adjustmentsTemplate() {")
page_end = js.find("  function adjustmentFindRow", page_start)
page = js[page_start:page_end]
if "loadRentalSettlementContext(state.period)" in page:
    fail("Worker Adjustments page still loads the settlement mega-context")
if "loadRentalAdjustmentPage(state.period)" not in page:
    fail("Worker Adjustments page does not load the dedicated bounded register")

for name in (
    "test_adjustment_register_is_server_paginated_with_exact_summary",
    "test_adjustment_create_returns_compact_delta_not_settlement_context",
):
    if name not in tests:
        fail(f"Django regression missing: {name}")

print("Verified SESCCO MS 1.0.116 Worker Adjustments page scale cutover: bounded register, aggregate KPIs, compact mutations, searchable scope filters and no settlement mega-context.")
