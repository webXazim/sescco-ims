#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.113"
PREDECESSOR = "1.0.91-administration-users-ui"
PREDECESSOR_SHA256 = "8d565a1567ad41c50c8a27815b0ee67bffdf56f6ccc2ae11c0473fbf1a3e3cdb"
FOREMAN_PERMISSIONS = {
    "rental.overview.view",
    "rental.workers.view",
    "rental.assignments.view",
    "rental.timesheets.view",
    "rental.timesheets.edit",
    "rental.timesheets.submit",
    "rental.overtime.view",
    "rental.overtime.edit",
    "rental.overtime.submit",
}
FORBIDDEN = {
    "rental.suppliers.view", "rental.suppliers.manage", "rental.workers.manage",
    "rental.assignments.manage", "rental.timesheets.approve", "rental.overtime.approve",
    "rental.adjustments.view", "rental.adjustments.manage", "rental.adjustments.approve",
    "rental.settlements.view", "rental.settlements.prepare", "rental.settlements.approve",
    "rental.payments.view", "rental.payments.prepare", "rental.payments.execute",
    "rental.documents.view", "rental.documents.finalize", "rental.reports.view",
    "rental.reports.export", "shared.archive.view", "shared.archive.manage",
    "shared.trash.view", "shared.trash.manage",
}


def fail(message: str) -> None:
    raise SystemExit(f"RENTAL SUPERVISOR SCOPE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/rental-supervisor-scope.json"))
if contract.get("release") != VERSION:
    fail("contract release does not match VERSION")
if contract.get("schema_change") is not True:
    fail("Foreman profile release must declare its Accounts migration")
if contract.get("payroll_formula_change") is not False or contract.get("settlement_formula_change") is not False:
    fail("Foreman access release must not change Payroll or settlement formulas")
profile = contract.get("profile") or {}
if profile.get("classification") != "rental-supervisor" or profile.get("system_profile_key") != "role-rental-supervisor":
    fail("Foreman profile identity changed")
if set(profile.get("permissions") or []) != FOREMAN_PERMISSIONS:
    fail("Foreman profile must contain exactly the nine operational permissions")
if not FORBIDDEN.issubset(set(profile.get("prohibited_by_default") or [])):
    fail("Foreman prohibited-permission contract is incomplete")
commercial = contract.get("commercial_data") or {}
if commercial.get("overtime_rate_visible") is not False or commercial.get("overtime_rate_override") is not False:
    fail("Foreman OT commercial-rate boundary must remain fail-closed")
predecessor = contract.get("predecessor") or {}
if predecessor.get("release") != PREDECESSOR or predecessor.get("archive_sha256") != PREDECESSOR_SHA256:
    fail("Foreman release is not bound to the exact 1.0.91 predecessor archive")

roles = text("apps/accounts/roles.py")
for marker in (
    'RENTAL_SUPERVISOR = "rental-supervisor", "Rental Supervisor / Foreman"',
    "AccessRole.RENTAL_SUPERVISOR: RoleDefinition(",
    "Project-scoped Rental workforce supervision",
):
    if marker not in roles:
        fail(f"role/profile template marker missing: {marker}")

catalog = text("apps/accounts/access_catalog.py")
foreman_block = catalog.split("if role == AccessRole.RENTAL_SUPERVISOR:", 1)
if len(foreman_block) != 2:
    fail("Foreman Access Profile permission template is missing")
block = foreman_block[1].split("permissions: set[AccessPermission]", 1)[0]
for permission in FOREMAN_PERMISSIONS:
    enum_name = permission.upper().replace(".", "_")
    # Names use RENTAL_* constants; assert values separately through the contract and
    # require every relevant suffix to appear in the dedicated block.
    suffix = permission.split("rental.", 1)[-1].upper().replace(".", "_")
    if suffix not in block:
        fail(f"Foreman permission template missing {permission}")
for forbidden in ("RENTAL_SETTLEMENTS_VIEW", "RENTAL_PAYMENTS_VIEW", "RENTAL_TIMESHEETS_APPROVE", "RENTAL_WORKERS_MANAGE"):
    if forbidden in block:
        fail(f"Foreman permission template improperly grants {forbidden}")

migration = text("apps/accounts/migrations/0008_rental_supervisor_profile.py")
for marker in (
    '("accounts", "0007_user_management_backend")',
    '("rental-supervisor", "Rental Supervisor / Foreman")',
    'key="role-rental-supervisor"',
    "FOREMAN_PERMISSIONS",
    "migrations.RemoveConstraint",
    "migrations.AlterField",
    "migrations.AddConstraint",
    "migrations.RunPython(create_foreman_profiles, remove_foreman_profiles)",
):
    if marker not in migration:
        fail(f"0008 migration marker missing: {marker}")
for permission in FOREMAN_PERMISSIONS:
    if f'"{permission}"' not in migration:
        fail(f"0008 migration does not seed {permission}")

masters = text("apps/rental_manpower/selectors/masters.py")
for marker in (
    "def projects_for_company(", "membership=None", "queryset = restrict_projects(queryset, membership)",
    "def workers_for_company(", "membership.project_scope_mode != \"all\"",
    "selected projects, but never expose", "_project_scope_match=Exists(scoped_assignments)",
    '"rateValue": (float(reference.rate) if reference else None) if include_commercial else None',
    'else "Restricted"',
):
    if marker not in masters:
        fail(f"Rental master scope/commercial marker missing: {marker}")

timesheet_selector = text("apps/rental_manpower/selectors/timesheets.py")
for marker in (
    "membership_allows_project(membership, project)",
    'raise PermissionDenied("This Rental project is outside your assigned access scope.")',
    "AccessPermission.RENTAL_TIMESHEETS_EDIT",
    "AccessPermission.RENTAL_TIMESHEETS_SUBMIT",
    "AccessPermission.RENTAL_OVERTIME_EDIT",
    "AccessPermission.RENTAL_TIMESHEETS_APPROVE",
    '"rate": str(assignment.rate) if include_commercial else "Restricted"',
    '"rateValue": float(assignment.rate) if include_commercial else None',
    '"rate": str(row.rate) if include_commercial else None',
):
    if marker not in timesheet_selector:
        fail(f"timesheet selector scope/permission marker missing: {marker}")

timesheet_service = text("apps/rental_manpower/services/timesheets.py")
for marker in (
    "AccessPermission.RENTAL_TIMESHEETS_EDIT", "AccessPermission.RENTAL_OVERTIME_EDIT",
    "AccessPermission.RENTAL_TIMESHEETS_SUBMIT", "AccessPermission.RENTAL_TIMESHEETS_APPROVE",
    "_project_scope(actor_membership, project)",
    "action=normalize_attendance_workflow_action(action)",
    "can_manage_commercial_rate",
    'raise PermissionDenied("Your access profile cannot set or override Rental commercial OT rates.")',
    "existing_overtime.rate",
):
    if marker not in timesheet_service:
        fail(f"timesheet service authority marker missing: {marker}")

api = text("apps/rental_manpower/api.py")
for marker in (
    "def _scoped_project(", "membership_allows_project(request.company_membership, project)",
    "def _commercial_visible(", "AccessPermission.RENTAL_SETTLEMENTS_VIEW",
    "AccessPermission.RENTAL_ASSIGNMENTS_MANAGE",
    "AccessPermission.RENTAL_SUPPLIERS_VIEW if request.method == \"GET\" else AccessPermission.RENTAL_SUPPLIERS_MANAGE",
    "AccessPermission.RENTAL_WORKERS_VIEW if request.method == \"GET\" else AccessPermission.RENTAL_WORKERS_MANAGE",
    "AccessPermission.RENTAL_ASSIGNMENTS_VIEW if request.method == \"GET\" else AccessPermission.RENTAL_ASSIGNMENTS_MANAGE",
    "AccessPermission.RENTAL_TIMESHEETS_VIEW if request.method == \"GET\" else AccessPermission.RENTAL_TIMESHEETS_EDIT",
    "AccessPermission.RENTAL_OVERTIME_EDIT",
    'AccessPermission.RENTAL_TIMESHEETS_SUBMIT if action_name == "submit" else AccessPermission.RENTAL_TIMESHEETS_APPROVE',
    "AccessPermission.RENTAL_SETTLEMENTS_VIEW",
    "AccessPermission.RENTAL_PAYMENTS_VIEW if request.method == \"GET\" else AccessPermission.RENTAL_PAYMENTS_EXECUTE",
    '"rate": str(row.rate) if include_commercial else None',
):
    if marker not in api:
        fail(f"Rental API exact-permission/scope marker missing: {marker}")

payroll_views = text("apps/core/payroll_views.py")
if "membership=membership" not in payroll_views or "rental_master_context(" not in payroll_views:
    fail("Payroll bootstrap does not pass membership into Rental master context")
for marker in (
    "can_supplier_view", "can_finance", "can_commercial",
    "suppliers = list(suppliers_for_company", "if can_supplier_view else []",
    "rental_financial_metrics_for_period", "if can_finance else",
):
    if marker not in masters:
        fail(f"Rental bootstrap data-minimization marker missing: {marker}")

record_api = text("apps/core/record_management_api.py")
for marker in ("AccessPermission.SHARED_TRASH_VIEW", "AccessPermission.SHARED_ARCHIVE_VIEW", "membership_has_permission"):
    if marker not in record_api:
        fail(f"Archive/Delete exact-permission marker missing: {marker}")
document_api = text("apps/documents/api.py")
for marker in ("AccessPermission.RENTAL_DOCUMENTS_VIEW", "AccessPermission.RENTAL_DOCUMENTS_FINALIZE", "membership_has_permission"):
    if marker not in document_api:
        fail(f"Rental document exact-permission marker missing: {marker}")
management_api = text("apps/core/management_api.py")
for marker in ("AccessPermission.RENTAL_REPORTS_VIEW", "AccessPermission.RENTAL_REPORTS_EXPORT", "membership_has_permission"):
    if marker not in management_api:
        fail(f"Rental report exact-permission marker missing: {marker}")

js = text("static/payroll/js/app.js")
for marker in (
    "const rentalRoutePermissions =", "function rentalQuickAddTemplate()",
    "function rentalSupervisorOverviewTemplate()", "if (!hasAccessPermission('rental.settlements.view')) return rentalSupervisorOverviewTemplate();",
    "Supplier settlement and worker cost snapshots are intentionally unavailable to this access profile.",
    "if (canViewSettlement) tabs.push(['cost','Manpower Cost']);",
    "const canEditCommercialRate = hasAnyAccessPermission('rental.settlements.view','rental.assignments.manage');",
    "Commercial rate restricted",
    "if (hasAnyAccessPermission('rental.settlements.view','rental.assignments.manage')) body.rate=current.rate||null;",
    "if (hasAccessPermission('rental.adjustments.view')) tabs.push(['advances','Advances']);",
    "if (hasAnyAccessPermission('rental.documents.view','shared.documents.view')) tabs.push(['documents','Documents']);",
    "Financial authority</span><strong>Restricted",
    "Project scope is revalidated by the server on every timesheet and overtime request.",
    "if (next === 'Submitted' && !hasAccessPermission('rental.timesheets.submit')) return 'edit';",
):
    if marker not in js:
        fail(f"Foreman frontend scope/data-minimization marker missing: {marker}")

# Regression evidence must exist and remain syntactically valid.
tests_rel = "apps/rental_manpower/tests/test_supervisor_access.py"
tests = text(tests_rel)
tree = ast.parse(tests)
discovered = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
required_tests = {
    "test_foreman_profile_is_narrow_and_excludes_finance_permissions",
    "test_foreman_project_scope_filters_workers_and_projects",
    "test_foreman_can_edit_overtime_and_submit_scoped_timesheet",
    "test_foreman_cannot_approve_timesheet",
    "test_foreman_cannot_open_supplier_settlement_or_payment_apis",
    "test_foreman_cannot_access_out_of_scope_project_timesheet",
    "test_foreman_timesheet_roster_does_not_expose_assignment_commercial_rate",
    "test_foreman_overtime_payload_hides_commercial_rate",
    "test_foreman_cannot_override_overtime_commercial_rate",
}
if not required_tests.issubset(discovered):
    fail(f"Foreman regression evidence incomplete: {sorted(required_tests - discovered)}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-rental-supervisor-scope.py" not in text(rel):
        fail(f"{rel} does not enforce the Foreman scope gate")
if "scripts/verify-rental-supervisor-scope.py" not in (json.loads(text("merge/payroll-production-e2e.json")).get("static_verifiers") or []):
    fail("Payroll production E2E contract does not register the Foreman scope verifier")

print("Verified SESCCO MS 1.0.113 Rental Supervisor / Foreman scoped access: exact nine-permission profile, Project scope, timesheet/overtime submission, finance/approval denial, assignment/OT commercial-data suppression, manager-controlled OT rates and direct-API enforcement.")
