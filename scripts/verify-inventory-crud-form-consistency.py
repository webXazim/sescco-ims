#!/usr/bin/env python3
"""Static safety contract for shared Inventory/Projects create/edit forms."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = [
    "templates/projects/project_form.html",
    "templates/inventory/stockitem_form.html",
    "templates/inventory/stock_addition_form.html",
    "templates/inventory/stock_usage_form.html",
    "templates/inventory/stock_adjustment_form.html",
    "templates/inventory/supplier_form.html",
    "templates/inventory/unit_form.html",
    "templates/inventory/transfer_form.html",
    "templates/inventory/movement_reversal_form.html",
    "templates/inventory/transfer_reverse.html",
    "templates/inventory/supplier_list.html",
    "templates/inventory/unit_list.html",
]
for name in TEMPLATES:
    text = (ROOT / name).read_text()
    assert 'data-crud-form' in text, f'{name} missing shared CRUD form'
    assert 'partials/crud_form_intro.html' in text, f'{name} missing form heading'
    assert 'partials/crud_form_actions.html' in text, f'{name} missing shared actions'
    assert '{% csrf_token %}' in text, f'{name} missing CSRF token'
    assert '<div class="form-actions">' not in text, f'{name} has legacy buttons'
for name in TEMPLATES[:7]:
    assert 'data-inventory-draft' in (ROOT / name).read_text(), f'{name} missing draft recovery'
for name in ['templates/projects/project_form.html', 'templates/inventory/stockitem_form.html']:
    text = (ROOT/name).read_text()
    assert 'novalidate data-inventory-draft' in text, f'{name} edit must support drafts'
script=(ROOT/'static/js/app.js').read_text()
assert 'data-crud-cancel' in script
assert 'dirty = false;' in script
validation=(ROOT/'static/platform/js/form-validation.js').read_text()
assert 'decorateCrudErrors' in validation and "aria-describedby" in validation
assert 'crud-form-actions' in (ROOT/'static/css/styles.css').read_text()
print('Inventory/Projects CRUD form consistency contract verified (10 workflows).')
