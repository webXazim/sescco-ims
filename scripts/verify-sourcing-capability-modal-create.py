"""Deployment contract: three directories reuse secured create forms inside native modals.

A static release guard only. Full browser/DB tests are required on staging.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]

def read(path):
    return (root / path).read_text(encoding="utf-8")

ui = read("static/sourcing/js/unified-directory.js")
lookup = read("static/sourcing/js/reference-lookup.js")
cap = read("templates/sourcing/unified/capabilities.html")
css = read("static/sourcing/css/unified-directory.css")
gateway = read("nginx/default.conf")

for token in (
    "data-modal-header-tools", ".sourcing-unified-cap-tools",
    "append(...tools.children)", "data-capability-create", "openCapabilityEditor(createAction)",
    "new DOMParser().parseFromString", "form.sourcing-form-shell",
    "sourcing:reference-lookup-mount", "X-CSRFToken", "new FormData(formElement)",
    "expectedDetail", "response.redirected", "editorDirty()", "data-editor-confirm",
    "storeEditorDraft()", "clearEditorDraft(editor.draftKey)", "beforeunload",
    "document.querySelector('.sourcing-reference-dialog[open]')",
):
    assert token in ui, f"Missing native capability modal behavior: {token}"
assert '<iframe' not in ui and 'frame.src' not in ui, "Keep X-Frame-Options protection"
assert 'add_header X-Frame-Options "DENY" always;' in gateway
assert 'closeButton.addEventListener(\'click\', requestClose)' in lookup
assert 'data-capability-refresh' in cap and 'data-capability-create' in cap
assert 'target="_blank"' not in cap
for route, button in (
    ("vendor_offer_create", "+ Add Supply Item"),
    ("workforce_offer_create", "+ Add Workforce"),
    ("subcontractor_service_create", "+ Add Service"),
):
    assert route in cap and button in cap
for kind, template in (
    ("vendors", "templates/sourcing/vendors/list.html"),
    ("manpower", "templates/sourcing/manpower/list.html"),
    ("subcontractors", "templates/sourcing/subcontractors/list.html"),
):
    html = read(template)
    assert "unified-directory.js" in html and "reference-lookup.js" in html, kind
    assert "reference-lookup.css" in html, kind
for marker in ("sourcing-capability-editor__body", "sourcing-unified-modal__header-controls", "sourcing-capability-editor__confirm"):
    assert marker in css, marker
print("PASS: native modal capability creation, quick-create close, and X-Frame-Options DENY preserved")
