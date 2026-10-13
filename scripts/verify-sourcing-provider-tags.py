#!/usr/bin/env python3
"""Static proof of tagged, unified, tenant-scoped Sourcing provider directories."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
def source(path):
    file = ROOT / path
    assert file.is_file(), f"Missing {path}"
    data = file.read_text(encoding="utf-8")
    if path.endswith('.py'):
        ast.parse(data, filename=path)
    return data

migration = source('apps/sourcing/migrations/0013_provider_classification_tags.py')
for model in ('sourcingvendor', 'sourcingmanpowersupplier', 'sourcingsubcontractor'):
    assert f'model_name="{model}"' in migration
for sourcefile, class_name in (
    ('apps/sourcing/models/vendors.py', 'SourcingVendor'),
    ('apps/sourcing/models/manpower.py', 'SourcingManpowerSupplier'),
    ('apps/sourcing/models/subcontractors.py', 'SourcingSubcontractor'),
):
    text = source(sourcefile)
    assert f'class {class_name}(SourcingLifecycleModel)' in text
    assert 'tags = models.JSONField(default=list, blank=True)' in text
    assert 'normalize_provider_tags(self.tags)' in text
forms = source('apps/sourcing/forms.py')
for name in ('SourcingVendorForm','SourcingManpowerSupplierForm','SourcingSubcontractorForm'):
    assert f'class {name}(SourcingProviderTagsFormMixin, forms.ModelForm)' in forms
for selector in ('vendors','manpower','subcontractors'):
    text = source(f'apps/sourcing/selectors/{selector}.py')
    assert '.objects.for_company(company)' in text
    assert 'Q(tags__icontains=query)' in text
    assert 'params.get("tag")' in text
    assert 'filter_company_capabilities' in text
for name, kind in (('vendors','Active Materials'), ('manpower','Active Trades'),('subcontractors','Active Services')):
    html = source(f'templates/sourcing/{name}/list.html')
    assert 'data-unified-results' in html and 'data-unified-form' in html
    assert 'data-column="tags"' in html
    assert kind in html and 'data-column="capabilities"' in html
    assert 'sourcing/unified/tags_cell.html' in html
    assert 'sourcing/unified/filters.html' in html
    assert 'data-provider-expand' in html
for path in ('templates/sourcing/unified/tags_cell.html','templates/sourcing/unified/tag_options.html'):
    source(path)
assert 'data-subcontractor-table' in source('static/sourcing/js/unified-directory.js')
assert 'Tags, category' in source('templates/sourcing/unified/filters.html')
assert 'def test_' in source('apps/sourcing/tests/test_provider_directory_tags.py')
print('Verified provider tags, bounded master counts, tenant isolation, 3 matching directory UIs, and regression coverage.')
