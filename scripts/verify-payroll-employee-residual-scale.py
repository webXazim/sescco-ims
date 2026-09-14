#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"EMPLOYEE RESIDUAL SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.83":
    fail(f"VERSION must be 1.0.83, found {version!r}")

contract = json.loads(text("merge/payroll-employee-residual-scale.json"))
if contract.get("release") != version:
    fail("employee residual-scale contract does not match VERSION")

directory = contract.get("employee_directory") or {}
if directory.get("page_sizes") != [25, 50, 100] or directory.get("default_page_size") != 50:
    fail("Internal Employee page-size contract changed")
if directory.get("browser_cache_limit") != 250:
    fail("Internal Employee browser cache must remain capped at 250 records")
if directory.get("ordinary_payment_scope") != "visible-page-only":
    fail("ordinary employee payment enrichment is no longer page-scoped")

api = text("apps/internal_payroll/api.py")
service = text("apps/internal_payroll/services/payment.py")
urls = text("apps/internal_payroll/urls.py")
js = text("static/payroll/js/app.js")

for rel, source in (("apps/internal_payroll/api.py", api), ("apps/internal_payroll/services/payment.py", service)):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "def employee_summary_api(request: HttpRequest) -> JsonResponse:",
    "def _employee_page_financial_context(*, company, employee_ids, period_value: str)",
    "def _employee_basic_salary_map(*, company, employee_ids)",
    "results, meta = serialize_list(rows, controls=controls, serializer=serialize_employee)",
    "page_ids = [row.get(\"id\") for row in results if row.get(\"id\")]",
    "employee_ids=page_ids",
    "if wps_filter and wps_filter != \"all\":",
):
    if needle not in api:
        fail(f"employee API scale protection missing: {needle}")
if "if period_value or (wps_filter" in api:
    fail("ordinary employee pages regressed to full salary-payment context hydration")
if 'path("api/internal/employees/summary/", api.employee_summary_api' not in urls:
    fail("employee summary endpoint is not routed")
if "employee_ids=None" not in service or "lines_qs = lines_qs.filter(employee_id__in=list(employee_ids))" not in service:
    fail("payment readiness cannot stay scoped to the visible employee page")
for needle in (
    'Prefetch("components", queryset=component_rows, to_attr="payment_components")',
    'Prefetch("adjustments", queryset=adjustment_rows, to_attr="payment_adjustments")',
    'getattr(line, "payment_components", None)',
    'getattr(line, "payment_adjustments", None)',
):
    if needle not in service:
        fail(f"bounded payment readiness lost snapshot prefetch protection: {needle}")

for needle in (
    "employeeDirectoryCacheLimit: 250",
    "employeeDirectoryCacheOrder: []",
    "function loadEmployeeDirectorySummary({force=false,render=true}={})",
    "function loadOrganizationEmployeeContext(kind,id,{force=false,render=true}={})",
    "page_size:'50'",
    "const context = organizationEmployeeContext('branch', branchId);",
    "const context = organizationEmployeeContext('department', departmentId);",
    "if ((!employee || !state.employeeProfileContexts[profileKey])",
    "employeeDirectorySummaryController: null",
    "organizationEmployeeControllers: new Map()",
    "state.employeeDirectorySummaryController?.abort()",
    "state.organizationEmployeeControllers.forEach(controller=>",
):
    if needle not in js:
        fail(f"browser residual-scale protection missing: {needle}")

route_start = js.find("    else if (route === 'branches' && branchId) {")
route_end = js.find("    else if (route === 'internal-employees' && employeeId) {", route_start)
if route_start < 0 or route_end < 0:
    fail("could not locate Branch/Department profile route block")
org_routes = js[route_start:route_end]
if "hydrateCompleteMaster('employees')" in org_routes:
    fail("Branch/Department profiles regressed to complete employee-master hydration")

merge_start = js.find("  function directoryEntityMerge(kind, rows) {")
merge_end = js.find("  function directoryFilterValueByName", merge_start)
if merge_start < 0 or merge_end < 0:
    fail("could not locate directoryEntityMerge")
merge_body = js[merge_start:merge_end]
for needle in ("const indexById=new Map", "employeeDirectoryCacheLimit", "collection.splice(index,1)"):
    if needle not in merge_body:
        fail(f"bounded employee-cache merge lost protection: {needle}")

print("Verified SESCCO MS 1.0.83 Internal Employee residual performance cutover: page-first enrichment, 250-record browser cache, server summaries and bounded organization profiles.")
