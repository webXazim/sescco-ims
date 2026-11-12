#!/usr/bin/env python3
"""Fail-closed authorization gate for project-inventory approval extension.

The original 94 and the Subcontractor 2 stay immutable. The 0016 migration
must contain precisely the 97 runtime permissions, and must grant the new
privilege only to the expected built-in profiles.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR_SHA = 'c8bbdfcd998f849bea9b1cdbc64560f243968e1cfc6fa6668459561742cd60ea'
NEW_PERMISSION = 'inventory.stock.approve'
EXPECTED_MANAGER = (
    'inventory.dashboard.view', 'inventory.stock.view', 'inventory.movements.view',
    'inventory.projects.view', 'inventory.locations.view', NEW_PERMISSION,
)


def fail(message):
    raise SystemExit('PROJECT INVENTORY ACCESS ERROR: ' + message)


def source(rel):
    path = ROOT / rel
    if not path.is_file():
        fail('missing: ' + rel)
    return path.read_text(encoding='utf-8')


def migration_permissions(text):
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'ALL_PERMISSIONS' for target in node.targets):
            return ast.literal_eval(node.value)
    fail('migration has no literal ALL_PERMISSIONS')


contract = json.loads(source('merge/project-inventory-approval-extension.json'))
expected_contract = {
    'extension_id': 'project-inventory-approval-2026-11-12',
    'predecessor_contract': 'merge/subcontractor-release-extension.json',
    'predecessor_permission_count': 96,
    'predecessor_sorted_permission_keys_sha256': PRIOR_SHA,
    'approved_added_permissions': [NEW_PERMISSION],
    'expected_effective_permission_count': 97,
    'accounts_grant_migration': 'apps/accounts/migrations/0016_project_manager_approval.py',
    'automatic_grant_profile_keys': ['role-owner', 'role-project-manager'],
    'project_manager_grants': list(EXPECTED_MANAGER),
    'historical_contracts_unchanged': True,
}
if contract != expected_contract:
    fail('project approval addendum is different from approved minimal extension')

retention = json.loads(source('merge/lifecycle-retention-contract.json'))
for label in ('inventory.StockApprovalRequest', 'inventory.StockApprovalDecision'):
    if retention.get('models', {}).get(label, {}).get('mode') != 'workflow_record_no_delete':
        fail(f'{label} must be recorded as workflow history with no ordinary delete')

catalog = source('apps/accounts/access_catalog.py')
block = catalog.split('class AccessPermission(StrEnum):', 1)[-1].split('_PERMISSION_LABELS', 1)[0]
keys = re.findall(r'^\s+[A-Z0-9_]+\s*=\s*"([^"]+)"', block, re.M)
if len(keys) != len(set(keys)) or len(keys) != 97 or NEW_PERMISSION not in keys:
    fail('expected exactly 97 unique permissions, including project stock approval')
prior = set(keys) - {NEW_PERMISSION}
if len(prior) != 96 or hashlib.sha256('\n'.join(sorted(prior)).encode('utf-8')).hexdigest() != PRIOR_SHA:
    fail('frozen historical 96 permissions changed')

previous = migration_permissions(source('apps/accounts/migrations/0013_subcontractor_sourcing_authority.py'))
if len(previous) != 96 or len(set(previous)) != 96 or set(previous) != prior:
    fail('historical 0013 migration has drifted')

migration = source('apps/accounts/migrations/0016_project_manager_approval.py')
current = migration_permissions(migration)
if len(current) != 97 or len(set(current)) != 97 or set(current) != set(keys):
    fail('0016 database CHECK constraint does not match the runtime 97-key catalog')
try:
    manager = ast.literal_eval(next(node.value for node in ast.parse(migration).body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MANAGER_PERMISSIONS' for t in node.targets)))
except (StopIteration, ValueError, TypeError):
    fail('0016 migration lacks literal project manager grants')
if manager != EXPECTED_MANAGER:
    fail('project manager profile permission scope changed')
required = (
    'dependencies = [("accounts", "0015_merge_subcontractor_authority")]',
    'RemoveConstraint(model_name="accessprofilepermission", name="accounts_profile_permission_valid")',
    'AddConstraint(model_name="accessprofilepermission"',
    'permission__in=ALL_PERMISSIONS',
    'Grant.objects.using(db).get_or_create(profile=profile, permission=permission)',
    'key="role-project-manager"',
    'filter(key="role-owner", is_system=True)',
    'permission="inventory.stock.approve"',
)
for marker in required:
    if marker not in migration:
        fail('missing 0016 schema/grant guard: ' + marker)
if migration.index('RemoveConstraint(model_name="accessprofilepermission"') > migration.index('AddConstraint(model_name="accessprofilepermission"'):
    fail('0016 must drop the previous constraint before installing the 97-key constraint')
if 'AccessPermission.INVENTORY_STOCK_APPROVE.value: AccessPermission.INVENTORY_STOCK_VIEW.value' not in source('apps/accounts/access_profiles.py'):
    fail('approval grant must require inventory stock view')
if 'INVENTORY_STOCK_APPROVE = "inventory.stock.approve"' not in catalog:
    fail('runtime permission symbol is missing')
# 0019 defined explicit BigAutoField primary keys, so the runtime models must
# retain the same explicit definition. Implicit Django IDs would produce a
# phantom 0020 AlterField migration on every production deploy.
model_tree = ast.parse(source('apps/inventory/models.py'))
migration_tree = ast.parse(source('apps/inventory/migrations/0019_approval_requests_and_unit_defaults.py'))
for model_name in ('StockApprovalRequest', 'StockApprovalDecision'):
    cls = next((node for node in model_tree.body if isinstance(node, ast.ClassDef) and node.name == model_name), None)
    if cls is None:
        fail(f'missing inventory model {model_name}')
    id_nodes = [node.value for node in cls.body if isinstance(node, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == 'id' for t in node.targets)]
    if len(id_nodes) != 1 or ast.unparse(id_nodes[0]) != 'models.BigAutoField(primary_key=True, serialize=False)':
        fail(f'{model_name}.id must explicitly match migration 0019; implicit ID triggers migration drift')
    # An explicit ID must be found in the historical CreateModel migration.
    create_models = [n for n in ast.walk(migration_tree) if isinstance(n, ast.Call)
                     and ast.unparse(n.func) == 'migrations.CreateModel'
                     and any(k.arg == 'name' and isinstance(k.value, ast.Constant) and k.value.value == model_name
                             for k in n.keywords)]
    if len(create_models) != 1:
        fail(f'migration 0019 missing {model_name} CreateModel')
    fields_kw = next((k.value for k in create_models[0].keywords if k.arg == 'fields'), None)
    matching = [field.elts[1] for field in (fields_kw.elts if isinstance(fields_kw, ast.List) else [])
                if isinstance(field, ast.Tuple) and len(field.elts) == 2
                and isinstance(field.elts[0], ast.Constant) and field.elts[0].value == 'id']
    if len(matching) != 1 or ast.unparse(matching[0]) != 'models.BigAutoField(primary_key=True, serialize=False)':
        fail(f'{model_name} migration 0019 ID declaration changed')

print('Verified project approval permission 97 = frozen 94 + 2 + 1; 0013 and 0016 constraints, owner/manager grants, and view dependency agree.')
