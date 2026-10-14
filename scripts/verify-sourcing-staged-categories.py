"""Static release guard for provider onboarding's shared unsaved categories.

Database-backed validation remains in test_staged_category_onboarding.py.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def read(path):
    return (root / path).read_text(encoding='utf-8')

helper = read('apps/sourcing/onboarding_categories.py')
assert 'pending_master_categories' in helper
assert 'DELETE' in helper and 'TOTAL_FORMS' in helper and 'min(100' in helper
forms = read('apps/sourcing/forms.py')
assert 'Choose an existing or staged category' in forms
provider = read('apps/sourcing/onboarding_forms.py')
assert 'categories=self.staged_categories' in provider
views = read('apps/sourcing/views.py')
assert views.count('pending_master_categories(') >= 2
assert 'membership_can_manage_sourcing_masters' in views
shared = read('static/sourcing/js/onboarding-staged-categories.js')
assert 'data-staged-category' in shared and 'draftCategoryDatalist' in shared
assert 'onboardingNewMaterial' in read('static/sourcing/js/vendor-onboarding.js')
assert 'stagedCategories?.refresh()' in read('static/sourcing/js/vendor-onboarding.js')
assert 'stagedCategories?.refresh()' in read('static/sourcing/js/provider-capability-onboarding.js')
for template in ('vendors', 'manpower', 'subcontractors'):
    page = read(f'templates/sourcing/{template}/form.html')
    assert 'onboarding-staged-categories.js' in page
    assert page.index('onboarding-staged-categories.js') < page.index(
        'vendor-onboarding.js' if template == 'vendors' else 'provider-capability-onboarding.js'
    )
print('Verified staged category reuse for Vendor Materials, Subcontractor Services and Manpower Trades.')
