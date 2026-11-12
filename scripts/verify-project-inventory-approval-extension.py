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
print('Verified project approval permission 97 = frozen 94 + 2 + 1; 0013 and 0016 constraints, owner/manager grants, and view dependency agree.')
