#!/usr/bin/env python3
"""Ensure a profile and directory use the same permission-checked modal implementation."""
from pathlib import Path
import re
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
    assert len(re.findall(r'{%\s*block\s+scripts\s*%}', detail)) == 1, (kind, 'profile scripts must have exactly one block')
    for asset in ('reference-lookup.js', 'capability-editor.js'):
        assert detail.count(asset) == 1, (kind, asset, 'script must load exactly once')
    if kind == 'vendors':
        assert detail.count('vendor-directory.js') == 1, 'Vendor directory behavior must be preserved'
# Catch duplicate named blocks anywhere in Sourcing templates before Django renders them.
for template in (r / 'templates/sourcing').rglob('*.html'):
    block_names = re.findall(r'{%\s*block\s+([a-zA-Z_][\w]*)\s*%}', template.read_text())
    assert len(block_names) == len(set(block_names)), f'Duplicate Django blocks in {template.relative_to(r)}'
assert "window.SourcingCapabilityEditor?.open" in read('static/sourcing/js/unified-directory.js')
print('PASS: six Sourcing views share the same native capability create modal and validation contract')
