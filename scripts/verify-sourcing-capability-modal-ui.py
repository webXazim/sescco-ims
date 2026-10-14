"""Contract check for compact Vendor, Service, and Workforce capability modal layouts.

This checks markup placement and focus/draft safeguards; run Django and browser
acceptance tests before deploying to production.
"""
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]

def source(path):
    return (ROOT / path).read_text(encoding="utf-8")

for path, marker in [
    ("templates/sourcing/vendors/onboarding_offer_row.html", "data-onboarding-staged-material"),
    ("templates/sourcing/unified/provider_onboarding_row.html", "data-onboarding-staged-master"),
]:
    html = source(path)
    # A normal HTML parser is enough to check element nesting: Django tags
    # are text nodes and do not affect these div boundaries.
    class Nesting(HTMLParser):
        def __init__(self):
            super().__init__(); self.stack = []; self.valid = False
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "div" and marker in attrs:
                self.valid |= any("sourcing-onboarding-reference" in a.get("class", "").split() for a in self.stack)
            if tag not in {"input", "img", "br", "hr", "meta", "link"}:
                self.stack.append({"tag": tag, **attrs})
        def handle_endtag(self, tag):
            while self.stack:
                node = self.stack.pop()
                if node["tag"] == tag: break
    nesting = Nesting()
    nesting.feed(html)
    assert nesting.valid, f"{path}: staged card must be inside picker area"
    assert html.count(marker) == 1, f"{path}: duplicate staged material element"
    assert 'data-onboarding-new-master' in html
    assert 'data-onboarding-existing-master' in html
    assert '<dialog class="sourcing-onboarding-material-dialog' in html
    assert 'data-material-confirm' in html and 'data-material-discard' in html

css = source("static/sourcing/css/vendor-onboarding.css")
assert '.sourcing-onboarding-reference:has(> .sourcing-onboarding-staged-material:not([hidden]))' in css
assert 'grid-column:1/-1' in css
assert '.sourcing-onboarding-staged-kicker' in css
assert '@media(max-width:520px)' in css

for view in ['vendors', 'manpower', 'subcontractors']:
    assert '?v=1.0.138' in source(f'templates/sourcing/{view}/form.html')

for path, state_key in [
    ('static/sourcing/js/vendor-onboarding.js', 'onboardingNewMaterial'),
    ('static/sourcing/js/provider-capability-onboarding.js', 'onboardingNewMaster'),
]:
    js = source(path)
    assert f'row.dataset.{state_key}' in js
    for marker in ['staged.hidden = !enabled', 'showWarning()', 'requestDismiss()', 'dialogMaster.showModal()', 'data-material-confirm']:
        assert marker in js, (path, marker)

print('PASS: All three capability modals render selected drafts inside picker cells, with responsive layout and draft-protection contracts.')
