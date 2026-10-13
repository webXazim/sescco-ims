#!/usr/bin/env python3
"""Dependency-free structural checks for the additive Sourcing foundation."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
models = ast.parse((root / 'apps/sourcing/models/subcontractors.py').read_text())
migration = ast.parse((root / 'apps/sourcing/migrations/0010_subcontractor_service_foundation.py').read_text())
expected = {
    'SourcingSubcontractor', 'SourcingSubcontractorContact', 'SourcingService',
    'SourcingSubcontractorService', 'SourcingSubcontractorServiceRevision',
}
model_names = {node.name for node in models.body if isinstance(node, ast.ClassDef)}
created = set()
all_operations = []
for node in ast.walk(migration):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'CreateModel', 'AddConstraint', 'AddIndex'}:
        operation = node.func.attr
        all_operations.append(operation)
        if operation == 'CreateModel':
            for kw in node.keywords:
                if kw.arg == 'name':
                    created.add(ast.literal_eval(kw.value))
assert created == expected, f'Wrong models in Sourcing migration: {created ^ expected}'
assert created <= model_names, f'Missing model implementation: {created - model_names}'
assert all_operations.count('AddConstraint') >= 9
assert all_operations.count('AddIndex') >= 10
source = (root / 'apps/sourcing/models/subcontractors.py').read_text()
for forbidden in ('apps.inventory', 'apps.internal_payroll', 'apps.rental_manpower', 'apps.projects', 'apps.documents'):
    assert forbidden not in source, f'Forbidden operational dependency: {forbidden}'
for marker in ('ImmutableSourcingRevisionManager', 'SourcingLifecycleModel', 'SourcingRateMixin', 'objects.for_company', 'Subcontractor belongs to another company.'):
    combined = source + (root / 'apps/sourcing/tests/test_subcontractor_foundation.py').read_text()
    assert marker in combined, f'Missing foundation guard: {marker}'
permission_src = (root / 'apps/accounts/access_catalog.py').read_text()
assert 'sourcing.subcontractors.view' not in permission_src, 'This release requires separate permission catalog certification.'
print('PASS: Upgrade 01 Sourcing schema structure, isolation checks, no premature permission release.')
