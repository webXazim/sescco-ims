#!/usr/bin/env python3
from __future__ import annotations
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.112"
PREDECESSOR_SHA = "1591e72505ceb6b3c9720dc62c53568eaf00ed9f624be255cb270af3ddb45425"


def fail(message: str) -> None:
    raise SystemExit(f"CROSS-MODULE ACCESS LEAK ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file(): fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

if text("VERSION").strip() != VERSION: fail("VERSION must be 1.0.112")
contract = json.loads(text("merge/cross-module-access-leak-closure.json"))
if contract.get("release") != VERSION: fail("contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA: fail("predecessor checksum changed")
if contract.get("schema_change") is not False: fail("1.0.112 must not introduce a database migration")
if contract.get("payroll_formula_change") is not False: fail("1.0.112 must not change Payroll formulas")

policy=text("apps/accounts/access_policy.py")
for marker in ('def branch_scope_ids(', 'def project_scope_ids(', 'def restrict_branch_snapshots(', 'def restrict_current_employee_branches(', 'def membership_has_company_wide_scopes('):
    if marker not in policy: fail(f"central scope helper missing: {marker}")

internal=text("apps/internal_payroll/api.py")
for marker in ('restrict_current_employee_branches(', 'membership=request.company_membership', 'INTERNAL_WPS_VIEW', 'can_salary =', 'can_payment ='):
    if marker not in internal: fail(f"Internal directory/profile leak closure missing: {marker}")
profile=text("apps/internal_payroll/selectors/employee_profile.py")
for marker in ('can_attendance =', 'can_adjustments =', 'can_payroll =', 'can_payments =', 'can_audit =', '"visibility": {'):
    if marker not in profile: fail(f"employee profile section authority missing: {marker}")

for rel in ("apps/documents/selectors/documents.py", "apps/documents/services/documents.py", "apps/documents/api.py"):
    body=text(rel)
    if 'branch_scope_ids' not in body and 'restrict_branch_snapshots' not in body: fail(f"Branch document scope missing: {rel}")
    if 'project_scope_ids' not in body and 'membership_allows_project' not in body and 'restrict_projects' not in body: fail(f"Project document scope missing: {rel}")
if '_assert_source_scope(' not in text("apps/documents/services/documents.py"): fail("finalization source scope is not enforced")

reports=text("apps/core/management/reports.py")
for marker in ('restrict_branch_snapshots(', 'restrict_current_employee_branches(', 'restrict_projects(', 'membership=None'):
    if marker not in reports: fail(f"report scope projection missing: {marker}")
management=text("apps/core/management_api.py")
for marker in ('def _report_type_permission(', 'membership_has_company_wide_scopes', '_management_overview_allowed', '_management_approvals_allowed', 'membership=membership'):
    if marker not in management: fail(f"Management/report exact authority missing: {marker}")

record=text("apps/core/selectors/record_management.py")
for marker in ('branch_scope_ids', 'project_scope_ids', 'membership=None'):
    if marker not in record: fail(f"Archive/Trash scope marker missing: {marker}")

rental=text("apps/rental_manpower/api.py")
for marker in ('project_scope_ids(request.company_membership)', 'rows = restrict_projects(', '_scoped_project(request, project_id)', 'scoped_project_ids is None'):
    if marker not in rental: fail(f"Rental indirect selector leak closure missing: {marker}")

frontend=text("static/payroll/js/app.js")
for marker in ("if(!hasAccessPermission('shared.search.use'))return;", "if(!hasAccessPermission('shared.search.use'))return [];", "const canEmployees=hasAccessPermission('internal.employees.view')", "const canWorkers=hasAccessPermission('rental.workers.view')", 'function managementAllowsRoute(route)'):
    if marker not in frontend: fail(f"global-search/navigation authority marker missing: {marker}")

rel="apps/accounts/tests/test_cross_module_access_leaks.py"
source=text(rel)
try: tree=ast.parse(source)
except SyntaxError as exc: fail(f"regression test file invalid: {exc}")
methods={node.name for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')}
required={
    'test_employee_only_profile_does_not_receive_attendance_payroll_payment_or_audit_profile_data',
    'test_branch_scoped_employee_list_hides_other_branch',
    'test_branch_scoped_employee_deep_link_hides_other_branch',
    'test_generic_reports_permission_does_not_unlock_wps_data',
    'test_generic_reports_permission_does_not_unlock_payments_data',
    'test_access_administrator_cannot_infer_management_financial_overview',
    'test_scoped_management_audit_fails_closed',
    'test_department_counts_are_limited_to_assigned_branch',
}
if not required.issubset(methods): fail(f"runtime regressions missing: {sorted(required-methods)}")
if "1.0.112" not in text("docs/CROSS_MODULE_ACCESS_LEAK_CLOSURE.md"): fail("operator/security guide not version-bound")
print("PASS: SESCCO MS 1.0.112 cross-module access leak closure verified across search, profiles, Documents, Reports, Management, Archive/Trash and scoped selectors.")
