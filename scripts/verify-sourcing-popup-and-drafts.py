#!/usr/bin/env python3
"""Release-contract check for unclipped provider tags and scoped draft warnings."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def get(name):
    return (ROOT / name).read_text(encoding='utf-8')

tag_js = get('static/sourcing/js/provider-tag-editor.js')
tag_css = get('static/sourcing/css/provider-tag-editor.css')
assert 'document.body.appendChild(options)' in tag_js
assert 'const positionOptions = () =>' in tag_js
assert 'flipAbove = below < naturalHeight && above > below' in tag_js
assert "document.addEventListener('scroll', repositionOnScroll" in tag_js
assert '.sourcing-tag-editor__suggestions{position:fixed' in tag_css
assert 'body > .sourcing-tag-editor__suggestions' in tag_css

vendor_form = get('templates/sourcing/vendors/form.html')
material_row = get('templates/sourcing/vendors/onboarding_offer_row.html')
onboarding_js = get('static/sourcing/js/vendor-onboarding.js')
assert 'data-onboarding-confirm' in vendor_form
assert 'Discard supply item changes?' in vendor_form
assert 'data-material-confirm' in material_row
assert 'Discard material changes?' in material_row
assert 'data-material-keep' in material_row and 'data-material-discard' in material_row
assert 'data-onboarding-keep' in vendor_form and 'data-onboarding-discard' in vendor_form
assert "dialogMaster.addEventListener('cancel'" in onboarding_js
assert "dialog.addEventListener('cancel'" in onboarding_js
assert 'event.stopPropagation()' in onboarding_js
for page in ('vendors','manpower','subcontractors'):
    html = get(f'templates/sourcing/{page}/form.html')
    assert 'provider-tag-editor.js' in html and 'provider-tag-editor.css' in html
    assert 'v=1.0.130' in html
print('Verified viewport-aware tag popup and independent material/supply draft confirmations.')
