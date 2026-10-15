#!/usr/bin/env python3
"""Static release contract for the two read-only Vendor Sourcing PDFs."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]

def read(filename):
    path = root / filename
    if not path.is_file():
        raise SystemExit(f'PDF EXPORT ERROR: missing {filename}')
    return path.read_text(encoding='utf-8')

views = read('apps/sourcing/views.py')
urls = read('apps/sourcing/urls.py')
report = read('apps/sourcing/pdf_exports.py')
list_html = read('templates/sourcing/vendors/list.html')
detail_html = read('templates/sourcing/vendors/detail.html')
script = read('static/sourcing/js/unified-directory.js')
tests = read('apps/sourcing/tests/test_vendor_pdf_exports.py')
url_helper = read('apps/sourcing/templatetags/sourcing_directory_urls.py')
for value in ('def vendor_directory_pdf(', 'def vendor_catalog_pdf(', '_can_export_dataset(_membership(request), "vendors")', '_can_export_dataset(_membership(request), "vendor_catalog")', 'for_company(request.company)', 'response["Cache-Control"] = "private, no-store"'):
    assert value in views, f'missing server PDF security contract: {value}'
for value in ('name="vendor_directory_pdf"', 'name="vendor_catalog_pdf"'):
    assert value in urls, f'missing PDF URL: {value}'
for value in ('LongTable(', 'repeatRows=1', 'MAX_PDF_ROWS = 10000', 'company_report_rows(', 'catalog_report_rows('):
    assert value in report, f'missing bounded PDF formatting/rows: {value}'
assert 'data-unified-export-pdf' in list_html
assert 'can_export_pdf' in detail_html and 'Export catalog PDF' in detail_html
assert "link.hasAttribute('data-unified-export-pdf')" in script
# Export URLs append a query suffix to a separately reversed route.  A helper
# that returns request.path when the query is empty breaks clean-page exports.
assert 'query_only=False' in url_helper and '("" if query_only else request.path)' in url_helper
for filename, expected in (
    ('templates/sourcing/vendors/list.html', 3),
    ('templates/sourcing/manpower/list.html', 3),
    ('templates/sourcing/subcontractors/list.html', 3),
):
    rows = [line for line in read(filename).splitlines() if 'data-unified-export' in line]
    assert len(rows) == expected and all('query_only=True' in line for line in rows), filename
assert 'test_directory_export_links_have_valid_paths_with_and_without_filters' in tests
assert 'class VendorPDFExportTests(TestCase)' in tests
print('PASS: Vendor PDFs are permission-gated, filtered, bounded and printable.')
