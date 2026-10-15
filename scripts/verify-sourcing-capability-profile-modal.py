#!/usr/bin/env python3
"""Ensure a profile and directory use the same permission-checked modal implementation."""
from pathlib import Path
r = Path(__file__).resolve().parents[1]
read = lambda p: (r / p).read_text()
ctrl = read('static/sourcing/js/capability-editor.js')
for item in ('data-sourcing-capability-modal', 'openCapabilityEditor(trigger,',
             'new FormData(formElement)', 'requestEditorClose()', 'data-editor-confirm',
             'sourcing:reference-lookup-mount', 'sourcing:capability-created',
             "response.status === 400", 'event.key === \'Tab\'',
             'sourcing-capability-editor__scroll'):
    assert item in ctrl, item
for kind in ('vendors', 'manpower', 'subcontractors'):
    for screen in ('list', 'detail'):
        tpl=read(f'templates/sourcing/{kind}/{screen}.html')
        assert 'capability-editor.js' in tpl and 'capability-editor.css' in tpl
        assert 'reference-lookup.js' in tpl
    detail=read(f'templates/sourcing/{kind}/detail.html')
    assert 'data-sourcing-capability-modal' in detail
    # Django template libraries are not inherited through {% extends %}.
    # All three profile templates use {% static %} to load the modal assets.
    assert '{% load static %}' in detail, f'{kind} profile must load the static tag library'
assert "window.SourcingCapabilityEditor?.open" in read('static/sourcing/js/unified-directory.js')
print('PASS: six Sourcing views share the same native capability create modal and validation contract')
