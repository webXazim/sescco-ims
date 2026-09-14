#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL QUERY HARDENING ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        fail(f"could not locate {start_marker!r}")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        end = len(source)
    return source[start:end]


version = text("VERSION").strip()
if version != "1.0.77":
    fail(f"VERSION must be 1.0.77, found {version!r}")

contract = json.loads(text("merge/payroll-query-hardening.json"))
if contract.get("release") != version:
    fail("query-hardening contract does not match VERSION")
if contract.get("database") != "postgresql" or contract.get("extension") != "pg_trgm":
    fail("PostgreSQL pg_trgm search contract changed")
if contract.get("migration_mode") != "concurrent-index-build":
    fail("search indexes must remain production-safe concurrent builds")

files = {
    "internal_selector": text("apps/internal_payroll/selectors/organization.py"),
    "attendance_selector": text("apps/internal_payroll/selectors/attendance.py"),
    "rental_selector": text("apps/rental_manpower/selectors/masters.py"),
    "assignment_selector": text("apps/rental_manpower/selectors/assignments.py"),
    "internal_model": text("apps/internal_payroll/models/organization.py"),
    "rental_master_model": text("apps/rental_manpower/models/masters.py"),
    "rental_assignment_model": text("apps/rental_manpower/models/assignments.py"),
    "internal_migration": text("apps/internal_payroll/migrations/0013_postgres_search_query_hardening.py"),
    "rental_migration": text("apps/rental_manpower/migrations/0009_postgres_search_query_hardening.py"),
}
for rel, source in files.items():
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is not valid Python: {exc}")

employee_search = block(files["internal_selector"], "def employees_for_company(", "\ndef serialize_branch")
for needle in (
    "assignment_match = EmployeeOrganizationAssignment.objects.for_company(company).filter(",
    "_assignment_search_match=Exists(assignment_search)",
    "_current_branch_match=Exists(current_assignment.filter(branch_id=branch_id))",
    "_current_department_match=Exists(current_assignment.filter(department_id=department_id))",
):
    if needle not in employee_search:
        fail(f"Internal employee query lost EXISTS hardening: {needle}")
if "return rows.distinct()" in employee_search or "organization_assignments__position__icontains" in employee_search:
    fail("Internal employee live search reintroduced join/DISTINCT fan-out")

attendance_search = block(files["attendance_selector"], "def attendance_period_context(", "\n    employee_ids =")
for needle in (
    'EmployeeOrganizationAssignment.objects.for_company(company)',
    '_assignment_search_match=Exists(assignment_search)',
    '_branch_period_match=Exists(period_assignments.filter(branch__name=branch))',
    '_department_period_match=Exists(period_assignments.filter(department__name=department))',
):
    if needle not in attendance_search:
        fail(f"Attendance query lost period-scoped EXISTS hardening: {needle}")
if ".distinct()" in attendance_search:
    fail("Attendance search reintroduced DISTINCT over assignment joins")

rental_worker_search = block(files["rental_selector"], "def workers_for_company(", "\ndef _assignment_rate_label")
for needle in (
    'worker_id=OuterRef("pk")',
    '_assignment_search_match=Exists(assignment_search)',
    '_current_project_match=Exists(current_assignments.filter(project_id=project_id))',
):
    if needle not in rental_worker_search:
        fail(f"Rental worker query lost EXISTS hardening: {needle}")
if ".distinct()" in rental_worker_search or "rental_assignments__trade__icontains" in rental_worker_search:
    fail("Rental worker live search reintroduced join/DISTINCT fan-out")

assignment_search = block(files["assignment_selector"], "def assignments_for_company(", "\ndef assignment_on_date")
for needle in (
    "matching_workers = (",
    "matching_projects = (",
    "Q(worker_id__in=Subquery(matching_workers))",
    "Q(project_id__in=Subquery(matching_projects))",
):
    if needle not in assignment_search:
        fail(f"Assignment activity search lost indexed subquery plan: {needle}")

expected_indexes = {
    "internal": {
        "int_emp_num_trgm", "int_emp_name_trgm", "int_emp_nid_trgm", "int_emp_phone_trgm",
        "int_org_pos_trgm", "int_org_open_branch_idx", "int_org_open_dept_idx",
    },
    "rental": {
        "rntl_wrk_num_trgm", "rntl_wrk_name_trgm", "rntl_wrk_nid_trgm", "rntl_wrk_phone_trgm",
        "rntl_asg_trade_trgm", "rntl_asg_reason_trgm", "rntl_asg_end_reason_trgm", "rntl_asg_live_project_idx",
    },
}
for needle in expected_indexes["internal"]:
    if needle not in files["internal_model"] or needle not in files["internal_migration"]:
        fail(f"Internal search index missing from model/migration: {needle}")
for needle in expected_indexes["rental"]:
    source = files["rental_master_model"] + files["rental_assignment_model"]
    if needle not in source or needle not in files["rental_migration"]:
        fail(f"Rental search index missing from model/migration: {needle}")
for migration in (files["internal_migration"], files["rental_migration"]):
    for needle in ("atomic = False", "TrigramExtension()", "AddIndexConcurrently("):
        if needle not in migration:
            fail(f"production-safe index migration contract missing: {needle}")

freeze = text("scripts/verify-production-freeze.sh")
release_tasks = text("scripts/release-tasks.sh")
for source_name, source in (("production freeze", freeze), ("release tasks", release_tasks)):
    if "verify-payroll-query-hardening.py" not in source:
        fail(f"{source_name} does not run the query-hardening verifier")

print("Payroll PostgreSQL search/query hardening contract verified.")
