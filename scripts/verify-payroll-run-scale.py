#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL RUN SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.113":
    fail(f"VERSION must be 1.0.113, found {version!r}")
contract = json.loads(text("merge/payroll-run-scale.json"))
if contract.get("release") != version:
    fail("Payroll Run scale contract does not match VERSION")

directory = contract.get("payroll_run_directory") or {}
if directory.get("page_sizes") != [25, 50, 100] or directory.get("default_page_size") != 50:
    fail("Payroll Run page-size contract changed")
if directory.get("saved_snapshot_prefetch_scope") != "visible-page-only":
    fail("saved Payroll Run details must remain visible-page-only")
if directory.get("previous_period_scope") != "visible-current-page-employees-only":
    fail("previous-period comparison regressed to an all-run payload")

selector = text("apps/internal_payroll/selectors/payroll.py")
api = text("apps/internal_payroll/payroll_api.py")
js = text("static/payroll/js/app.js")
tests = text("apps/internal_payroll/tests/test_payroll.py")
for rel, source in (("apps/internal_payroll/selectors/payroll.py", selector), ("apps/internal_payroll/payroll_api.py", api), ("apps/internal_payroll/tests/test_payroll.py", tests)):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "PAYROLL_RUN_PAGE_SIZES = {25, 50, 100}",
    "def payroll_run_page_context(",
    "def _page_snapshot_lines(",
    "queryset[offset : offset + page_size].prefetch_related(",
    "def _comparison_rows(",
    ".filter(run=previous_run, employee_id__in=employee_ids)",
    '"surface": "payroll_run_page"',
    '"summary": summary',
    '"reviewSummary": review_summary',
):
    if needle not in selector:
        fail(f"bounded Payroll Run selector protection missing: {needle}")

for needle in (
    'request.GET.get("surface")',
    "payroll_run_page_context(",
    'if str(body.get("surface") or "").strip().lower() == "run"',
):
    if needle not in api:
        fail(f"Payroll Run API cutover protection missing: {needle}")

for needle in (
    "payrollPage: 1",
    "payrollPageSize: Number(localStorage.getItem('payroll-ui-run-page-size') || 50)",
    "payrollServer: { key:'', pendingKey:'', controller:null, requestId:0, loading:false, error:'', meta:{} }",
    "function payrollRunRequest(period = state.period)",
    "function cancelPayrollRunRequest()",
    "async function loadPayrollRunPage(period = state.period",
    "surface:'run'",
    "data-payroll-page=",
    "id=\"payrollPageSize\"",
    "state.payrollPage=1",
    "beforeRender:()=>cancelPayrollRunRequest()",
    "payload?.surface === 'payroll_run_page'",
    "Number(payrollContextForPeriod().reviewSummary?.Critical",
):
    if needle not in js:
        fail(f"Payroll Run browser-scale protection missing: {needle}")

runs_start = js.find("  function payrollRunsTemplate() {")
runs_end = js.find("  function openPayrollDetailDrawer", runs_start)
if runs_start < 0 or runs_end < 0:
    fail("could not locate Payroll Runs renderer")
runs_body = js[runs_start:runs_end]
if "payrollFilteredRows(allRows)" in runs_body:
    fail("Payroll Runs regressed to browser-side filtering of the current run")
if "const branchOptions = ['All branches', ...Array.from(new Set(allRows.map" in runs_body:
    fail("Payroll Runs regressed to deriving filter options from all browser rows")

if "test_payroll_run_page_context_pages_saved_snapshot_before_detail_prefetch" not in tests:
    fail("Django regression for bounded Payroll Run pages is missing")

print("Verified SESCCO MS 1.0.113 Payroll Run scale cutover: bounded current/previous rows, server search/filter/pagination, exact totals and global review authority.")
