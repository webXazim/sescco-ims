#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"SALARY SETUP SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.79":
    fail(f"VERSION must be 1.0.79, found {version!r}")
contract = json.loads(text("merge/payroll-salary-setup-scale.json"))
if contract.get("release") != version:
    fail("salary-setup scale contract does not match VERSION")

directory = contract.get("salary_structure_directory") or {}
if directory.get("page_sizes") != [25, 50, 100] or directory.get("default_page_size") != 50:
    fail("Salary Structure page-size contract changed")
if directory.get("complete_employee_master_required") is not False:
    fail("Salary Setup must not require a complete employee master")
if directory.get("complete_structure_history_required") is not False:
    fail("Salary Setup must not require all-company structure history")

api = text("apps/internal_payroll/salary_api.py")
js = text("static/payroll/js/app.js")
tests = text("apps/internal_payroll/tests/test_salary_api.py")
for rel, source in (("apps/internal_payroll/salary_api.py", api), ("apps/internal_payroll/tests/test_salary_api.py", tests)):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    'controls = parse_list_controls(',
    'max_page_size=100',
    'employees = employees_for_company(',
    'employee_results, meta = serialize_list(employees, controls=controls, serializer=serialize_employee)',
    'current_salary_structures_for_company(company=request.company).filter(employee_id__in=page_ids)',
    'meta["coverage"] = {',
    '"employeeCount": int(employee_count)',
    '"configuredCount": int(configured_count)',
    'if employee_id:',
    '"history": history, "current": current',
):
    if needle not in api:
        fail(f"bounded salary API protection missing: {needle}")

setup_start = js.find("  function salarySetupTemplate() {")
setup_end = js.find("  function salaryComponentsTab() {", setup_start)
if setup_start < 0 or setup_end < 0:
    fail("could not locate Salary Setup renderer")
setup_body = js[setup_start:setup_end]
if "hydrateCompleteMaster('employees')" in setup_body:
    fail("Salary Setup regressed to complete employee-master hydration")

load_start = js.find("  async function loadSalarySetup({force=false}={}) {")
load_end = js.find("  function directoryPagination", load_start)
if load_start < 0 or load_end < 0:
    fail("could not locate Salary Setup loader")
load_body = js[load_start:load_end]
if "appApi('/api/internal/salary/structures/')" in load_body:
    fail("Salary Setup loader regressed to unpaged all-structure history fetch")

for needle in (
    "salaryStructureDirectory: {results:[]",
    "salaryStructureDirectoryEmployeeIds: []",
    "function salaryStructureRequest()",
    "async function loadSalaryStructureDirectory({force=false,render=true}={})",
    "function cancelSalaryStructureRequest({clearPending=true}={})",
    "async function loadSalaryStructureHistory(employeeId,{force=false,render=false}={})",
    "page_size:String(store.pageSize||50)",
    "if(state.salaryStructureSearch.trim())params.set('q',state.salaryStructureSearch.trim())",
    "salaryStructureSetupFilter",
    "data-salary-structure-page",
    "salaryStructurePageSize",
    "id=\"salaryStructureEmployeeSearch\"",
    "page_size:'25'",
    "state.salaryStructureHistoryLoaded.add(employeeId)",
    "!state.salaryStructureHistoryLoaded.has(employeeId))delete state.salaryStructures[employeeId]",
):
    if needle not in js:
        fail(f"Salary Setup browser scale protection missing: {needle}")

structures_start = js.find("  function salaryStructuresTab() {")
structures_end = js.find("  function salaryOvertimeTab() {", structures_start)
if structures_start < 0 or structures_end < 0:
    fail("could not locate Employee Structures tab")
structures_body = js[structures_start:structures_end]
if "state.employees.filter" in structures_body:
    fail("Employee Structures tab regressed to browser-side complete employee filtering")

if "test_salary_structure_directory_is_bounded_and_history_is_employee_scoped" not in tests:
    fail("Django regression for bounded Salary Structure directory is missing")

print("Verified SESCCO MS 1.0.79 Salary Setup scale cutover: employee-first pagination, server search/coverage and lazy per-employee salary history.")
