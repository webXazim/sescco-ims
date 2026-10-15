#!/usr/bin/env python3
"""Static safety contract for shared Sourcing capability dialogs.

Does not replace Django integration or interactive browser testing.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def read(path):
    return (root / path).read_text(encoding="utf-8")

ui = read("static/sourcing/js/unified-directory.js")
editor = read("static/sourcing/js/capability-editor.js")
lookup = read("static/sourcing/js/reference-lookup.js")
capabilities = read("templates/sourcing/unified/capabilities.html")
css = read("static/sourcing/css/capability-editor.css")
gateway = read("nginx/default.conf")

for token in ("data-modal-header-tools", "append(...tools.children)",
              "data-capability-create", "window.SourcingCapabilityEditor?.open", "data-capability-refresh"):
    assert token in ui or token in capabilities, token
for token in ("window.SourcingCapabilityEditor", "data-sourcing-capability-modal",
              "new DOMParser().parseFromString", "form.sourcing-form-shell",
              "sourcing:reference-lookup-mount", "X-CSRFToken", "new FormData(formElement)",
              "expectedDetail", "response.redirected", "editorDirty()", "data-editor-confirm",
              "storeEditorDraft()", "clearEditorDraft(editor.draftKey)", "beforeunload",
              "document.querySelector('.sourcing-reference-dialog[open]')"):
    assert token in editor, f"Missing shared modal behavior: {token}"
assert '<iframe' not in editor and 'frame.src' not in editor
assert 'add_header X-Frame-Options "DENY" always;' in gateway
assert "closeButton.addEventListener('click', requestClose)" in lookup
assert 'data-capability-refresh' in capabilities and 'data-capability-create' in capabilities
assert 'target="_blank"' not in capabilities
for route in ('vendor_offer_create', 'workforce_offer_create', 'subcontractor_service_create'):
    assert route in capabilities
for kind, route in (
    ('vendors', 'vendor_offer_create'),
    ('manpower', 'workforce_offer_create'),
    ('subcontractors', 'subcontractor_service_create'),
):
    listing = read(f'templates/sourcing/{kind}/list.html')
    detail = read(f'templates/sourcing/{kind}/detail.html')
    for filename, html in (('list', listing), ('detail', detail)):
        assert 'capability-editor.js' in html and 'capability-editor.css' in html, (kind, filename)
        assert 'reference-lookup.js' in html and 'reference-lookup.css' in html, (kind, filename)
    assert 'unified-directory.js' in listing
    assert 'data-sourcing-capability-modal' in detail and route in detail
for token in ('sourcing-capability-editor__scroll', 'sourcing-capability-editor__head',
              'sourcing-capability-editor__confirm', 'sourcing-form-actions',
              'sourcing-form-section'):
    assert token in css or token in editor, token
print('PASS: Vendor/Manpower/Subcontractor use the shared native capability modal, audited routes, and discard protection')
