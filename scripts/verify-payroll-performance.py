#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL PERFORMANCE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(text("merge/payroll-performance.json"))
if contract.get("release") != "1.0.62":
    fail("performance contract release must be 1.0.62")
profile = contract.get("benchmark_profile", {})
if profile != {"internal_employees": 2000, "rental_workers": 5000, "months": 12}:
    fail("benchmark profile no longer matches the 1.0.61 scale contract")
if contract.get("query_budgets") != {"internal_context_max_queries": 40, "rental_context_max_queries": 40}:
    fail("query budgets changed without an explicit performance upgrade")

attendance_selector = text("apps/internal_payroll/selectors/attendance.py")
attendance_service = text("apps/internal_payroll/services/attendance.py")
payroll_service = text("apps/internal_payroll/services/payroll.py")
rental_timesheets = text("apps/rental_manpower/selectors/timesheets.py")
rental_settlement_selector = text("apps/rental_manpower/selectors/settlements.py")
rental_settlement_service = text("apps/rental_manpower/services/settlements.py")
perf_command = text("apps/core/management/commands/payroll_performance_report.py")
freeze = text("scripts/verify-production-freeze.sh")

for rel, source in (
    ("apps/internal_payroll/selectors/attendance.py", attendance_selector),
    ("apps/internal_payroll/services/attendance.py", attendance_service),
    ("apps/internal_payroll/services/payroll.py", payroll_service),
    ("apps/rental_manpower/selectors/timesheets.py", rental_timesheets),
    ("apps/rental_manpower/selectors/settlements.py", rental_settlement_selector),
    ("apps/rental_manpower/services/settlements.py", rental_settlement_service),
    ("apps/core/management/commands/payroll_performance_report.py", perf_command),
):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is not valid Python: {exc}")

required_attendance = (
    'Prefetch("salary_structures", queryset=salary_structures, to_attr="attendance_salary_structures")',
    'prefetched = getattr(employee, "attendance_salary_structures", None)',
)
for needle in required_attendance:
    if needle not in attendance_selector:
        fail(f"Internal Attendance lost set-wise salary prefetch: {needle}")

for needle in (
    "def _overtime_sources_locked(",
    "overtime_structures, overtime_lines = _overtime_sources_locked(",
):
    if needle not in attendance_service:
        fail(f"Internal overtime lost set-wise source loading: {needle}")

for needle in (
    "def _locked_calculation_sources(",
    'source_maps = _locked_calculation_sources(',
    'PayrollRunLine.objects.bulk_create(payroll_lines, batch_size=500)',
    'PayrollRunLineComponent.objects.bulk_create(component_snapshots, batch_size=1000)',
    'PayrollRunLineAdjustment.objects.bulk_create(adjustment_snapshots, batch_size=1000)',
    'components_by_line: dict[object, list[PayrollRunLineComponent]]',
    'adjustments_by_line: dict[object, list[PayrollRunLineAdjustment]]',
):
    if needle not in payroll_service:
        fail(f"Internal Payroll lost high-cardinality hardening: {needle}")

# Regression guard: snapshot integrity must not put child SELECTs back inside the run-line loop.
snapshot_start = payroll_service.index("def _snapshot_payload_locked")
snapshot_end = payroll_service.index("def _clear_run_snapshot_locked", snapshot_start)
snapshot = payroll_service[snapshot_start:snapshot_end]
loop_start = snapshot.index("for row in rows:")
if ".objects.select_for_update()" in snapshot[loop_start:]:
    fail("Payroll snapshot fingerprint reintroduced per-line SELECT FOR UPDATE queries")

for needle in (
    "assignments_by_worker={}",
    "for a in assignments_by_worker.get(wid, []):",
):
    if needle not in rental_timesheets:
        fail(f"Rental Timesheet lost linear assignment grouping: {needle}")

for needle in (
    "supplier_scope_rows = list(",
    'suppliers_by_period.setdefault(row["period_id"], []).append(row)',
    '"adjustmentsByWorker": adjustments_by_worker',
):
    if needle not in rental_settlement_selector:
        fail(f"Rental settlement selector lost high-cardinality hardening: {needle}")

if 'rental_adjustments_by_worker(company=company, period_start=start)' in rental_settlement_selector:
    fail("Rental settlement context reintroduced a duplicate adjustment query")

for needle in (
    'SupplierSettlementLine.objects.bulk_create(settlement_lines, batch_size=1000)',
    'SupplierSettlementRateLine.objects.bulk_create(rate_snapshot_lines, batch_size=1000)',
    'SupplierSettlementAdjustmentLine.objects.bulk_create(adjustment_snapshot_lines, batch_size=1000)',
    "rates_by_line: dict[object, list[dict[str, object]]]",
    "adjustments_by_line: dict[object, list[dict[str, object]]]",
):
    if needle not in rental_settlement_service:
        fail(f"Rental settlement service lost high-cardinality hardening: {needle}")

for needle in (
    "CaptureQueriesContext(connection)",
    'default=40',
    'Payroll query budgets are within the configured limits.',
):
    if needle not in perf_command:
        fail(f"runtime performance report missing contract: {needle}")

if "verify-payroll-performance.py" not in freeze:
    fail("production freeze does not run the Payroll performance verifier")

print("Payroll high-cardinality performance contract verified.")
