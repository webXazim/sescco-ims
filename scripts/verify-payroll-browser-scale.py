#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL BROWSER SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.117":
    fail(f"VERSION must be 1.0.117, found {version!r}")

contract = json.loads(text("merge/payroll-browser-scale.json"))
if contract.get("release") != version:
    fail("browser-scale contract does not match VERSION")
if contract.get("benchmark_volume") != {
    "internal_employees": 2000,
    "rental_workers": 5000,
    "history_months": 12,
}:
    fail("benchmark volume contract changed")
limits = contract.get("browser_limits") or {}
for key in ("directory_page_sizes", "timesheet_page_sizes", "assignment_page_sizes"):
    if set(limits.get(key) or []) != {25, 50, 100}:
        fail(f"{key} must stay 25/50/100")
if limits.get("bootstrap_internal_employees") != 50 or limits.get("bootstrap_rental_workers") != 50:
    fail("thin bootstrap must stay at 50 Internal / 50 Rental masters")
if limits.get("global_search_results_per_entity") != 5:
    fail("global search must stay bounded to 5 results per entity")
if limits.get("search_debounce_ms") != 320:
    fail("large-data search debounce must stay at 320 ms")
if limits.get("max_assignment_activity_events_per_100_segments") != 200:
    fail("assignment activity expansion bound changed")
if int(limits.get("max_context_payload_bytes") or 0) > 2_500_000:
    fail("browser payload budget was loosened above 2.5 MB")

# Every earlier large-data contract must be carried into the final freeze.
for rel in (
    "merge/payroll-directory-runtime.json",
    "merge/payroll-assignment-runtime.json",
    "merge/payroll-timesheet-scale.json",
    "merge/payroll-bootstrap-search.json",
    "merge/payroll-query-hardening.json",
):
    data = json.loads(text(rel))
    if data.get("release") != version:
        fail(f"{rel} is not carried forward to {version}")

js = text("static/payroll/js/app.js")
for needle in (
    "serverDirectories: {",
    "rentalAssignmentServer: {",
    "attendanceServer: { key:'', pendingKey:'', controller:null, requestId:0",
    "rentalTimesheetServer: { key:'', pendingKey:'', controller:null, requestId:0",
    "globalSearchServer: { controller:null, requestId:0",
    "const controller=new AbortController();",
    "const controller = new AbortController();",
    "setTimeout(()=>loadGlobalSearch(value),320)",
    "page=1&page_size=5",
    "Rows <select id=\"timesheetPageSize\"",
    "Rows <select id=\"rentalTimesheetPageSize\"",
    "data-assignment-page-size=",
):
    if needle not in js:
        fail(f"browser-scale source protection missing: {needle}")

# Critical routes must not regress to full workforce scans.
assignment_start = js.find("  function rentalAssignmentsTemplate() {")
assignment_end = js.find("  function rentalWorkforceTemplate() {", assignment_start)
if assignment_start < 0 or assignment_end < 0:
    fail("could not locate Rental Assignment Lifecycle template")
assignment_route = js[assignment_start:assignment_end]
for forbidden in ("state.rentalWorkers.filter", "rentalAssignmentActivityRows()", "rentalAssignmentIntegrity()"):
    if forbidden in assignment_route:
        fail(f"Assignment Lifecycle regressed to full-browser scan: {forbidden}")

timesheet_start = js.find("  function rentalTimesheetDailyTemplate() {")
timesheet_end = js.find("\n  function rentalOvertimeRegisterTemplate() {", timesheet_start)
if timesheet_start < 0 or timesheet_end < 0:
    fail("could not locate Rental Timesheet template")
timesheet_route = js[timesheet_start:timesheet_end]
for forbidden in ("state.rentalWorkers.filter", "rentalAssignmentsInProjectPeriod(worker,state.rentalTimesheetProject,state.period)"):
    if forbidden in timesheet_route:
        fail(f"Rental Timesheet regressed to full workforce scan: {forbidden}")

# Backend page limits must remain hard-capped at 100.
for rel in (
    "apps/internal_payroll/attendance_api.py",
    "apps/rental_manpower/api.py",
):
    source = text(rel)
    if "100" not in source:
        fail(f"{rel} no longer contains the bounded 100-row API cap")
if "max_page_size=100" not in text("apps/rental_manpower/api.py"):
    fail("Assignment Lifecycle API lost max_page_size=100")
if "bounded_size = max(1, min(100" not in text("apps/internal_payroll/selectors/attendance.py"):
    fail("Internal Attendance selector lost 100-row cap")
if "bounded_size = max(1, min(100" not in text("apps/rental_manpower/selectors/timesheets.py"):
    fail("Rental Timesheet selector lost 100-row cap")

# Runtime/report and live-browser certification utilities must remain valid Python.
for rel in (
    "apps/core/management/commands/payroll_browser_scale_report.py",
    "scripts/certify-payroll-browser-scale.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

report = text("apps/core/management/commands/payroll_browser_scale_report.py")
for needle in (
    'page_size=100',
    'include_summary=False',
    'internal_count < 2000',
    'rental_count < 5000',
    'max_payload_bytes',
    'max_context_queries',
):
    if needle not in report:
        fail(f"runtime browser-scale report lost protection: {needle}")

browser_runner = text("scripts/certify-payroll-browser-scale.py")
for needle in (
    '"internal", "timesheets", "#timesheetSearch"',
    '"rental", "rental-assignments", "#rentalAssignmentSearch"',
    '"rental", "timesheets", "#rentalTimesheetSearch"',
    '"internal", "salary-setup"',
    '"internal", "payroll-runs"',
    'route="adjustments"',
    'route="payments"',
    'route="bank-export"',
    'route="wps"',
    'route="documents"',
    'open_route("internal", "reports"',
    'route="management-audit"',
    'result_count > 30',
    'rows > 100',
    'rows > 200',
):
    if needle not in browser_runner:
        fail(f"live browser certification lost scenario/bound: {needle}")

freeze = text("scripts/verify-production-freeze.sh")
release_tasks = text("scripts/release-tasks.sh")
for source_name, source in (("production freeze", freeze), ("release tasks", release_tasks)):
    if "verify-payroll-browser-scale.py" not in source:
        fail(f"{source_name} does not enforce browser-scale freeze")

production_e2e = json.loads(text("merge/payroll-production-e2e.json"))
labels = set(production_e2e.get("runtime_test_labels") or [])
if "apps.core.tests.test_payroll_browser_scale" not in labels:
    fail("production E2E suite does not include browser-scale contract test")
scenario_ids = {row.get("id") for row in production_e2e.get("scenarios") or []}
if "browser-scale-runtime-regression" not in scenario_ids:
    fail("production E2E contract does not include browser-scale regression scenario")

print("Payroll 5K/2K browser-scale contract verified.")
