#!/usr/bin/env python3
"""Release addendum gate: permitted Subcontractor delta without rewriting 1.0.117."""
from __future__ import annotations
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'sourcing.subcontractors.view', 'sourcing.subcontractors.manage'}
FROZEN_SHA = '5779eb3e368b736267df841db18ba8b3df92073b528acdf9abdb3447fd7a4481'

def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')

def require(condition, msg):
    if not condition:
        raise SystemExit('SUBCONTRACTOR RELEASE GATE ERROR: ' + msg)

historical = json.loads(read('merge/granular-access-authority.json'))
extension = json.loads(read('merge/subcontractor-release-extension.json'))
require(historical['release'] == '1.0.117' and historical['permission_catalog_size'] == 94, 'historical permission freeze changed')
require(extension['approved_added_permissions'] == sorted(EXPECTED), 'unexpected Subcontractor grant set')
require(extension['legacy_sorted_permission_keys_sha256'] == FROZEN_SHA, 'legacy fingerprint changed')
require(extension['legacy_permission_catalog_size'] == 94 and extension['expected_effective_permission_count'] == 96, 'permission totals changed')
require(extension['automatic_grant_scope'] == 'role-owner-only', 'automatic permission elevation not approved')
require(extension['operational_domain_mutation_allowed'] is False, 'operational mutation was enabled')
require(extension['database_and_browser_staging_certification_required'] is True, 'staging requirement removed')
require(extension['historical_browser_contract_unchanged'] is True, 'old browser freeze changed')
require(json.loads(read('merge/sourcing-browser-e2e-production-freeze.json'))['permission_catalog_size'] == 94, 'historical E2E permission contract rewritten')

catalog_src = read('apps/accounts/access_catalog.py')
block = catalog_src.split('class AccessPermission(StrEnum):', 1)[1].split('_PERMISSION_LABELS', 1)[0]
keys = re.findall(r'^\s+[A-Z0-9_]+\s*=\s*"([^\"]+)"', block, re.M)
require(len(keys) == len(set(keys)) == 96, 'catalog must have exactly 96 unique grants')
require(EXPECTED <= set(keys), 'new grants missing')
old_keys = set(keys) - EXPECTED
require(len(old_keys) == 94 and hashlib.sha256('\n'.join(sorted(old_keys)).encode()).hexdigest() == FROZEN_SHA, 'original 94 grants drifted')

migration_src = read('apps/accounts/migrations/0013_subcontractor_sourcing_authority.py')
tree = ast.parse(migration_src)
perms = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ALL_PERMISSIONS' for t in node.targets):
        perms = ast.literal_eval(node.value)
require(perms is not None and len(perms) == 96 and set(perms) == set(keys), 'DB constraint migration does not match the exact catalog')
require('RemoveConstraint' in migration_src and 'AddConstraint' in migration_src, 'permission database constraint must be updated')
require("key='role-owner', is_system=True" in migration_src, 'automatic owner grant scope changed')
require('get_or_create(profile_id=profile.pk, permission=permission)' in migration_src, 'owner grants must be idempotent')
require("('accounts', '0012_sourcing_access_control_authority')" in migration_src, 'permission migration ordering changed')

profiles_src = read('apps/accounts/access_profiles.py')
require('AccessPermission.SOURCING_SUBCONTRACTORS_MANAGE.value: AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value' in profiles_src,
        'Subcontractor manage/view permission dependency missing')
for rel in ('apps/sourcing/urls.py', 'apps/sourcing/views.py', 'apps/sourcing/access.py',
            'apps/sourcing/services/subcontractors.py','apps/sourcing/services/subcontractor_catalog.py',
            'apps/sourcing/services/subcontractor_documents.py',
            'apps/sourcing/exchange.py'):
    ast.parse(read(rel), filename=rel)
for rel in ('apps/sourcing/models/subcontractors.py', 'apps/sourcing/models/__init__.py'):
    source = read(rel)
    require('SourcingSubcontractor' in source, f'missing subcontractor models: {rel}')
    require(not re.search(r'ForeignKey\s*\(\s*(?:Project|StockItem|RentalWorker|Payroll)', source), 'operational FK introduced')
for rel in ('apps/sourcing/tests/test_subcontractor_directory.py',
            'apps/sourcing/tests/test_subcontractor_catalog.py',
            'apps/sourcing/tests/test_subcontractor_verification.py',
            'apps/sourcing/tests/test_subcontractor_qualifications.py',
            'apps/sourcing/tests/test_subcontractor_data_exchange.py'):
    require('def test_' in read(rel), 'missing runtime regressions ' + rel)
require('sourcing.SourcingSubcontractorDocument' in read('merge/lifecycle-retention-contract.json'), 'qualification retention classification missing')
print('Verified additive 94+2 permission contract, matching DB constraint, owner-only grants, retention, isolated Sourcing domain, and regression test presence.')
