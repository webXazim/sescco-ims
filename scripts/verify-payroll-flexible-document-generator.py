from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / 'apps/documents/api.py').read_text()
urls = (ROOT / 'apps/documents/urls.py').read_text()
js = (ROOT / 'static/payroll/js/app.js').read_text()
css = (ROOT / 'static/payroll/css/v2/prs-records-management-cutover.css').read_text()
notes = (ROOT / 'RELEASE_NOTES.md').read_text()

required_api = [
    'document_generation_options_api',
    'document_generation_plan_api',
    'document_generation_execute_api',
    'RENTAL_GENERATABLE_DOCUMENT_TYPES',
    '_rental_generation_candidates',
    'selected_keys',
    'Create at most 200 documents in one batch',
]
required_urls = [
    'api/documents/generation-options/',
    'api/documents/generation-plan/',
    'api/documents/generate/',
]
required_js = [
    'openRentalDocumentGeneratorDrawer',
    'reviewRentalDocumentGeneration',
    'executeRentalDocumentGeneration',
    'rental-generator-type',
    'rental-generator-suppliers',
    'rental-generator-projects',
    'Record Supplier Invoice Received',
    'Create ${newItems.length.toLocaleString()} Document',
]
required_css = ['document-generator-types', 'document-generator-filters', 'document-generator-plan']

for token in required_api:
    if token not in api:
        raise SystemExit(f'FLEXIBLE DOCUMENT GENERATOR ERROR: API token missing: {token}')
for token in required_urls:
    if token not in urls:
        raise SystemExit(f'FLEXIBLE DOCUMENT GENERATOR ERROR: URL missing: {token}')
for token in required_js:
    if token not in js:
        raise SystemExit(f'FLEXIBLE DOCUMENT GENERATOR ERROR: frontend token missing: {token}')
for token in required_css:
    if token not in css:
        raise SystemExit(f'FLEXIBLE DOCUMENT GENERATOR ERROR: CSS token missing: {token}')
if 'data-document-batch-timesheets>Supplier Timesheets' in js or 'data-document-batch-settlements>Settlement Statements' in js:
    raise SystemExit('FLEXIBLE DOCUMENT GENERATOR ERROR: rigid top-level batch buttons remain')
if '# 1.0.117 — Flexible Rental Document Generator Hotfix\n' not in notes:
    raise SystemExit('FLEXIBLE DOCUMENT GENERATOR ERROR: release notes lost the flexible generator section')
print('Verified SESCCO MS 1.0.117 flexible Rental document generator: multi-type, supplier/project scoped, review-before-create and idempotent bounded batch execution.')
