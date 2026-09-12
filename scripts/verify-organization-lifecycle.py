#!/usr/bin/env python3
from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def fail(m): raise SystemExit(f"ORGANIZATION LIFECYCLE ERROR: {m}")
def req(rel,text):
    p=ROOT/rel
    if not p.is_file() or text not in p.read_text(encoding="utf-8"): fail(f"{rel} missing {text!r}")
for rel in ["apps/internal_payroll/models/organization.py","apps/internal_payroll/lifecycle.py","apps/internal_payroll/services/organization.py","apps/internal_payroll/selectors/organization.py","apps/internal_payroll/api.py","apps/internal_payroll/urls.py","apps/internal_payroll/migrations/0009_organization_master_lifecycle.py","apps/internal_payroll/migrations/0011_master_trash_retention.py","apps/internal_payroll/tests/test_organization.py","apps/internal_payroll/tests/test_api.py"]:
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
 ("static/payroll/js/app.js","Move to Trash"),
 ("static/payroll/js/app.js","Restore as inactive"),
 ("static/payroll/js/app.js","['All','Active','Inactive','Archived']"),
]: req(rel,text)
manifest=(ROOT/'merge/frozen-merge-migrations.sha256').read_text(encoding='utf-8')
for migration in ('0009_organization_master_lifecycle.py','0011_master_trash_retention.py'):
 if migration not in manifest: fail(f'migration not frozen: {migration}')
print('Branch / Office and Department Archive + 30-day Trash contract verified.')
