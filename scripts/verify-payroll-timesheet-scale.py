#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL TIMESHEET SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.82":
    fail(f"VERSION must be 1.0.82, found {version!r}")

contract = json.loads(text("merge/payroll-timesheet-scale.json"))
if contract.get("release") != version:
    fail("timesheet-scale contract does not match VERSION")
if set(contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("timesheet page-size contract changed")
if contract.get("search_debounce_ms") != 320:
    fail("timesheet search debounce must remain 320 ms")

attendance_api = text("apps/internal_payroll/attendance_api.py")
attendance_selector = text("apps/internal_payroll/selectors/attendance.py")
rental_api = text("apps/rental_manpower/api.py")
rental_selector = text("apps/rental_manpower/selectors/timesheets.py")
bootstrap = text("apps/core/payroll_views.py")
js = text("static/payroll/js/app.js")
internal_tests = text("apps/internal_payroll/tests/test_attendance_api.py")
rental_tests = text("apps/rental_manpower/tests/test_timesheets.py")

for needle in (
    "def _bounded_page(",
    'if page_size not in {25, 50, 100}:',
    'query=request.GET.get("q", "")',
    'branch=request.GET.get("branch", "")',
    'department=request.GET.get("department", "")',
    '"deltaOnly": True',
    '"changes": [',
    'membership=request.company_membership',
    'include_summary=request.GET.get("summary", "1") != "0"',
):
    if needle not in attendance_api:
        fail(f"Internal Attendance scale protection missing: {needle}")

for needle in (
    "def attendance_period_summary(",
    "def attendance_period_context(",
    "Paginator(roster_qs, bounded_size)",
    "employee_ids = [employee.pk for employee in roster]",
    "include_summary: bool = True",
):
    if needle not in attendance_selector:
        fail(f"Internal Attendance selector is no longer bounded: {needle}")

if "page=1,\n            page_size=50," not in bootstrap:
    fail("initial Payroll attendance bootstrap is no longer bounded to 50 rows")

for needle in (
    "def _bounded_timesheet_page(",
    'if page_size not in {25, 50, 100}:',
    'query=request.GET.get("q", "")',
    'supplier_id=request.GET.get("supplier_id", "")',
    'include_summary=request.GET.get("summary", "1") != "0"',
    '"deltaOnly": True',
    'payload["changes"] = [',
):
    if needle not in rental_api:
        fail(f"Rental Timesheet scale protection missing: {needle}")

for needle in (
    "def _project_worker_queryset(",
    "def rental_timesheet_summary(",
    "def rental_timesheet_context(",
    "Paginator(workers_qs, bounded_size)",
    "worker_ids = [worker.pk for worker in workers]",
    "include_summary: bool = True",
):
    if needle not in rental_selector:
        fail(f"Rental Timesheet selector is no longer bounded: {needle}")

for needle in (
    "attendanceServer: {",
    "rentalTimesheetServer: {",
    "const controller = new AbortController();",
    "const controller = new AbortController();",
    "params.set('page_size'",
    "params.set('summary'",
    "rentalTimesheetRoster",
    "queueMicrotask(() => loadInternalAttendancePeriod(state.period))",
    "queueMicrotask(() => loadRentalTimesheet({ render:true }))",
    "delay:320,beforeRender:()=>{cancelInternalAttendanceRequest()",
    "delay:320,beforeRender:()=>{cancelRentalTimesheetRequest()",
    "Attendance page exported",
    "Timesheet page exported",
):
    if needle not in js:
        fail(f"frontend timesheet scale protection missing: {needle}")

for function_name in ("internalTimesheetPageData", "rentalTimesheetPageData"):
    start = js.find(f"  function {function_name}(")
    end = js.find("\n  function ", start + 10)
    if start < 0 or end < 0:
        fail(f"could not locate {function_name}")
    block = js[start:end]
    if ".slice(" in block:
        fail(f"{function_name} returned to browser-side roster slicing")
    if ".meta" not in block or "count" not in block:
        fail(f"{function_name} is not using server pagination metadata")

start = js.find("  function rentalTimesheetDailyTemplate() {")
end = js.find("\n  function rentalOvertimeRegisterTemplate() {", start)
if start < 0 or end < 0:
    fail("could not locate Rental Timesheet route template")
rental_route = js[start:end]
for forbidden in (
    "state.rentalWorkers.filter",
    "rentalAssignmentsInProjectPeriod(worker,state.rentalTimesheetProject,state.period)",
):
    if forbidden in rental_route:
        fail(f"Rental Timesheet returned to full browser workforce scanning: {forbidden}")

if "test_get_period_is_server_paged_and_searchable" not in internal_tests:
    fail("Internal Attendance paging regression coverage is missing")
if "test_timesheet_api_is_server_paged_and_returns_project_roster_only" not in rental_tests:
    fail("Rental Timesheet paging regression coverage is missing")
if "test_timesheet_patch_returns_small_delta_not_full_project_month" not in rental_tests:
    fail("Rental Timesheet mutation-delta regression coverage is missing")

print("Verified Attendance/Timesheet scale cutover: bounded 25/50/100 server pages, cancellation-aware filters, project-period Rental rosters, aggregate summaries and small mutation deltas.")
