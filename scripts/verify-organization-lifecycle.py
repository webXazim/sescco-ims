#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def fail(m): raise SystemExit(f"ORGANIZATION LIFECYCLE ERROR: {m}")
def req(rel,text):
    p=ROOT/rel
    if not p.is_file() or text not in p.read_text(encoding="utf-8"): fail(f"{rel} missing {text!r}")
for rel in ["apps/internal_payroll/models/organization.py","apps/internal_payroll/lifecycle.py","apps/internal_payroll/services/organization.py","apps/internal_payroll/selectors/organization.py","apps/internal_payroll/api.py","apps/internal_payroll/urls.py","apps/internal_payroll/migrations/0009_organization_master_lifecycle.py","apps/internal_payroll/migrations/0011_master_trash_retention.py","apps/internal_payroll/migrations/0012_reversible_archive_lifecycle.py","apps/internal_payroll/tests/test_organization.py","apps/internal_payroll/tests/test_api.py"]:
    ast.parse((ROOT/rel).read_text(encoding="utf-8"))
for rel,text in [
 ("apps/internal_payroll/models/organization.py","class BranchKind(models.TextChoices):"),
 ("apps/internal_payroll/models/organization.py","archived_reason = models.CharField(max_length=300, blank=True)"),
 ("apps/internal_payroll/lifecycle.py","class BranchLifecyclePolicy"),
 ("apps/internal_payroll/lifecycle.py","class DepartmentLifecyclePolicy"),
 ("apps/internal_payroll/services/organization.py","def archive_branch("),
 ("apps/internal_payroll/services/organization.py","def delete_unused_branch("),
 ("apps/internal_payroll/services/organization.py","def archive_department("),
 ("apps/internal_payroll/services/organization.py","def delete_unused_department("),
 ("apps/internal_payroll/api.py","def branch_lifecycle_api("),
 ("apps/internal_payroll/api.py","def department_lifecycle_api("),
 ("apps/internal_payroll/urls.py",'name="branch-lifecycle-api"'),
 ("apps/internal_payroll/urls.py",'name="department-lifecycle-api"'),
 ("static/payroll/js/app.js","function openOrganizationLifecycleDrawer"),
 ("static/payroll/js/app.js","Delete with 30-day recovery"),
 ("static/payroll/js/app.js","Restore previous state"),
 ("apps/internal_payroll/services/organization.py",'"cascade_scope": "current_employees"'),
 ("apps/internal_payroll/services/organization.py","deleted_at=cascade_deleted_at, purge_after=cascade_purge_after"),
 ("apps/internal_payroll/selectors/organization.py",'"cascadeLifecycle"'),
 ("apps/internal_payroll/selectors/organization.py","_inherited_deleted=Exists"),
 ("apps/internal_payroll/selectors/organization.py","_inherited_archived=Exists"),
 ("static/payroll/js/app.js","['All','Active','Inactive','Archived']"),
]: req(rel,text)
# PostgreSQL does not allow SELECT ... FOR UPDATE on a DISTINCT outer query.
# Parent-delete cascades must first resolve current assignment employee ids and
# then lock the employee table directly. This gate protects the production
# seed/delete path that exercises real Branch and Department cascades.
service_path = ROOT / "apps/internal_payroll/services/organization.py"
service_source = service_path.read_text(encoding="utf-8")
service_tree = ast.parse(service_source)
for function_name in ("delete_unused_branch", "delete_unused_department"):
    node = next(
        (item for item in service_tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function_name),
        None,
    )
    if node is None:
        fail(f"missing lifecycle service {function_name}")
    segment = ast.get_source_segment(service_source, node) or ""
    if "select_for_update()" not in segment:
        fail(f"{function_name} must lock cascade employee rows")
    if ".distinct()" in segment:
        fail(f"{function_name} cannot combine SELECT FOR UPDATE with DISTINCT on PostgreSQL")
    if "EmployeeOrganizationAssignment.objects.filter(" not in segment or 'pk__in=current_employee_ids' not in segment:
        fail(f"{function_name} must resolve assignment ids before locking employees")

manifest=(ROOT/'merge/frozen-merge-migrations.sha256').read_text(encoding='utf-8')
for migration in ('0009_organization_master_lifecycle.py','0011_master_trash_retention.py','0012_reversible_archive_lifecycle.py'):
 if migration not in manifest: fail(f'migration not frozen: {migration}')
print('Branch / Office and Department reversible cascade Archive + 30-day Delete contract verified.')
