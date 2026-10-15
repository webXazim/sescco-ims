#!/usr/bin/env python3
"""Check all provider PDF routes, templates and security contracts before deployment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(name):
    path = ROOT / name
    if not path.is_file():
        raise SystemExit(f"PROVIDER PDF ERROR: missing {name}")
    return path.read_text()

urls = read("apps/sourcing/urls.py")
views = read("apps/sourcing/views.py")
reports = read("apps/sourcing/pdf_exports.py")
script = read("static/sourcing/js/unified-directory.js")
tests = read("apps/sourcing/tests/test_provider_pdf_parity.py")

for kind, directory, catalog, dataset, master_dataset, listfile, detailfile in (
    ("manpower", "manpower_directory_pdf", "workforce_catalog_pdf", "manpower_suppliers", "workforce_catalog", "templates/sourcing/manpower/list.html", "templates/sourcing/manpower/detail.html"),
    ("subcontractor", "subcontractor_directory_pdf", "subcontractor_catalog_pdf", "subcontractors", "subcontractor_service_catalog", "templates/sourcing/subcontractors/list.html", "templates/sourcing/subcontractors/detail.html"),
):
    directory_template = read(listfile)
    detail_template = read(detailfile)
    for token in (f'name="{directory}"', f'name="{catalog}"'):
        assert token in urls, f"Missing {kind} URL: {token}"
    for token in (f"def {directory}(", f"def {catalog}(",
                  f'_can_export_dataset(_membership(request), "{dataset}")',
                  f'_can_export_dataset(_membership(request), "{master_dataset}")'):
        assert token in views, f"Missing {kind} export permission: {token}"
    assert f"'sourcing:{directory}'" in directory_template
    assert 'data-unified-export-pdf' in directory_template and 'query_only=True' in directory_template
    assert f"'sourcing:{catalog}'" in detail_template
    assert 'SOURCING_ACCESS.export' in detail_template
    assert f'def render_{directory}(' in reports
    assert f'def render_{catalog}(' in reports
assert 'MAX_PDF_ROWS = 10000' in reports
assert 'for_company(request.company)' in views
assert 'link.hasAttribute(\'data-unified-export-pdf\')' in script
assert 'test_individual_catalog_exports_tenant_scoped_and_active_only' in tests
assert 'test_export_authority_required_besides_provider_view' in tests
assert 'test_directory_pdf_link_valid_filtered_and_unfiltered' in tests
print('PASS: Provider PDF parity, permissions, tenant scope and bounded reports.')
