#!/usr/bin/env python3
"""Offline contract checks for countable quantity policy, stable sort and wheel guard."""
from pathlib import Path
import ast
import importlib.util
import sys

root = Path(__file__).resolve().parent.parent

def assert_contains(relative, string):
    body = (root / relative).read_text(encoding='utf-8')
    assert string in body, f'Missing {string!r} from {relative}'

spec = importlib.util.spec_from_file_location('quantity_policy', root / 'apps/inventory/quantity_policy.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from decimal import Decimal
assert module.is_named_countable('Pieces', 'pc')
assert module.is_named_countable('Laptops', 'pcs')
assert not module.is_named_countable('Kilograms', 'kg')
assert module.is_whole(Decimal('1.000'))
assert not module.is_whole(Decimal('0.999'))
assert not module.is_whole(Decimal('1.99'))
assert not module.is_whole(Decimal('NaN'))
assert_contains('apps/inventory/forms.py', '("created", "Recently added first")')
assert_contains('apps/inventory/forms.py', '("oldest-created", "Oldest added first")')
for f in ('apps/inventory/views.py','apps/data_exchange/services/exporting.py'):
    assert_contains(f, '"created": ("-created_at", "-pk")')
    assert_contains(f, '"oldest-created": ("created_at", "pk")')
for f in ('templates/inventory/stockitem_list.html', 'templates/inventory/office_inventory.html'):
    assert_contains(f, 'data-default-sort="created"')
    assert_contains(f, '<label for="id_sort">Sort</label>')
for f in ('templates/base.html', 'templates/project_pulse/base.html', 'templates/sourcing/base.html',
          'templates/accounts/administration.html', 'templates/payroll/app.html',
          'templates/registration/login.html', 'templates/registration/change_password.html'):
    assert_contains(f, 'prevent-wheel-value-changes.js')
assert_contains('static/platform/js/prevent-wheel-value-changes.js', 'event.preventDefault()')
assert_contains('apps/inventory/migrations/0020_enforce_countable_units.py', 'def enforce_countable')
assert_contains('apps/inventory/management/commands/reconcile_countable_balance.py', '--apply')
for file in root.rglob('*.py'):
    if '__pycache__' in file.parts: continue
    try:
        ast.parse(file.read_text(encoding='utf-8'), filename=str(file))
    except SyntaxError as exc:
        print(f'Syntax check failed in {file}: {exc}', file=sys.stderr)
        sys.exit(1)
print('Passed Inventory quantity, new-first sorting, export parity, and wheel guard contract checks.')
