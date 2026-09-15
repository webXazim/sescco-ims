#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL BOOTSTRAP/SEARCH VERIFY FAILED: {message}")


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.86":
    fail(f"VERSION must be 1.0.86, found {version!r}")

contract = json.loads(text("merge/payroll-bootstrap-search.json"))
if contract.get("release") != version:
    fail("bootstrap/search contract release does not match VERSION")
if contract.get("bootstrap", {}).get("internal_employee_limit") != 50:
    fail("Internal bootstrap must stay bounded to 50 employee masters")
if contract.get("bootstrap", {}).get("rental_worker_limit") != 50:
    fail("Rental bootstrap must stay bounded to 50 worker masters")
if contract.get("global_search", {}).get("results_per_entity_type") != 5:
    fail("global search entity result limit must stay at 5")
if contract.get("global_search", {}).get("debounce_ms") != 320:
    fail("global search debounce must stay at 320 ms")

views = text("apps/core/payroll_views.py")
for required in (
    "employee_limit=50",
    "worker_limit=50, include_assignments=False",
    '"deferred": bool(can_internal)',
):
    if required not in views:
        fail(f"missing thin bootstrap marker: {required}")
if "salary_setup_context(company=request.company)" in views:
    fail("Payroll shell must not eagerly serialize the complete salary setup")
if "payroll_period_context(" in views[views.index("def payroll_app"):]:
    fail("Payroll shell must not eagerly serialize the complete payroll period")
if "salary_payment_context(" in views[views.index("def payroll_app"):]:
    fail("Payroll shell must not eagerly serialize salary payment readiness")

internal_selector = text("apps/internal_payroll/selectors/organization.py")
for required in ("employee_limit: int | None = None", '"bootstrapComplete"', '"bootstrapEmployeeCount"'):
    if required not in internal_selector:
        fail(f"Internal master selector missing {required}")
rental_selector = text("apps/rental_manpower/selectors/masters.py")
for required in ("worker_limit: int | None = None", "include_assignments: bool = True", '"bootstrapWorkerCount"'):
    if required not in rental_selector:
        fail(f"Rental master selector missing {required}")

app = text("static/payroll/js/app.js")
for required in (
    "async function hydrateCompleteMaster(kind",
    "async function loadSalarySetup(",
    "async function loadGlobalSearch(query)",
    "new AbortController()",
    "setTimeout(()=>loadGlobalSearch(value),320)",
    "page=1&page_size=5",
    "globalSearchEndpointSpecs",
    "directoryEntityMerge(spec.kind,rows)",
    "async function loadRentalWorkerProfile(workerId",
    "loadEmployeeProfileContext(employeeId, state.period",
):
    if required not in app:
        fail(f"frontend missing thin-bootstrap/search behavior: {required}")
search_start = app.index("  function globalSearchPageRows(query)")
search_end = app.index("\n  const drawerTemplates = {", search_start)
search_block = app[search_start:search_end]
for forbidden in ("state.employees.map(", "state.rentalWorkers.map("):
    if forbidden in search_block:
        fail(f"global search regressed to full browser master scan: {forbidden}")

internal_api = text("apps/internal_payroll/api.py")
if '"employee": serialize_employee(employee)' not in internal_api:
    fail("employee deep-link profile API must return the employee master")
rental_api = text("apps/rental_manpower/api.py")
if '@require_http_methods(["GET", "PATCH", "DELETE"])' not in rental_api:
    fail("rental worker detail endpoint must support GET for thin-bootstrap deep links")
if '"assignments": serialized_assignment_history' not in rental_api:
    fail("rental worker detail GET must return assignment history")

print("Verified SESCCO MS 1.0.86 thin Payroll bootstrap and server-backed global search contract.")
