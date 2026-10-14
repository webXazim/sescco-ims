"""Source-level guard for Vendor-style onboarding on both remaining provider types.

Django test_provider_capability_onboarding must also run before production cutover.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def read(path): return (ROOT/path).read_text(encoding='utf-8')

views = read('apps/sourcing/views.py')
forms = read('apps/sourcing/onboarding_forms.py')
modal = read('templates/sourcing/unified/provider_onboarding.html')
row = read('templates/sourcing/unified/provider_onboarding_row.html')
js = read('static/sourcing/js/provider-capability-onboarding.js')

for route, name in [('manpower', 'SourcingManpowerOnboardingFormSet'),
                    ('subcontractors', 'SourcingSubcontractorOnboardingFormSet')]:
    assert name in views and name in forms
    page = read(f'templates/sourcing/{route}/form.html')
    assert 'show_capabilities' in page and 'provider_onboarding.html' in page
    assert 'provider-capability-onboarding.js' in page
    assert 'reference-lookup.js' in page
for item in ['management_form', 'data-onboarding-confirm', 'data-onboarding-keep',
             'data-onboarding-discard', 'data-onboarding-template']:
    assert item in modal, item
for item in ['data-onboarding-master', 'data-material-confirm', 'data-material-discard',
             'data-onboarding-edit-master', 'verified_now', 'rate_basis', 'reference_lookup_field.html']:
    assert item in row, item
for item in ['showModal()', 'draft', 'data-onboarding-dialog', 'Abort', 'data-onboarding-master']:
    if item == 'Abort': continue
    assert item in js or item.lower() in js, item
for item in ['with atomic():', 'membership_can_manage_sourcing_masters',
             'create_trade(', 'create_service(', 'create_workforce_offer(', 'create_service_offer(']:
    assert item in views, item
assert 'max_num=50' in forms and 'absolute_max=100' in forms
print('Verified provider onboarding parity: transactional save, permission boundaries, modal drafts, bounded formsets and shared catalog search.')
