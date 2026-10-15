#!/usr/bin/env python3
"""Static source contract for bounded shared lookup, modal discard and Sourcing form recovery."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def text(path):
    p = ROOT / path
    if not p.is_file():
        raise SystemExit(f"SOURCING LOOKUP/DRAFT ERROR: missing {path}")
    return p.read_text(encoding='utf-8')
lookup = text('static/sourcing/js/reference-lookup.js')
for check in ('[data-reference-more]', 'Load more results', "url.searchParams.set('page'", 
              'sourcing-reference-discard-confirm', 'Discard unsaved changes?',
              'beforeunload', 'sessionStorage.setItem(draftKey', 'savedDraft.values', 'sourcing:reference-lookup-restore'):
    if check not in lookup:
        raise SystemExit(f"SOURCING LOOKUP/DRAFT ERROR: missing lookup feature: {check}")
backend = text('apps/sourcing/views.py')
for check in ('offset = (page - 1) * 12', 'matches[offset:offset + 13]', '"has_more": len(window) > 12',
              'queryset.filter(', 'request.company'):
    if check not in backend:
        raise SystemExit(f"SOURCING LOOKUP/DRAFT ERROR: missing bounded query: {check}")
drafts = text('static/sourcing/js/sourcing-page-draft.js')
for check in ('sessionStorage.setItem(key', "sourcing:reference-lookup-restore", 'beforeunload', "data-sourcing-page-draft", 'visibilitychange'):
    if check not in drafts:
        raise SystemExit(f"SOURCING LOOKUP/DRAFT ERROR: missing recovery behavior: {check}")
for name in ('vendors/offer_form.html', 'manpower/workforce_form.html',
             'subcontractors/service_form.html', 'materials/form.html',
             'services/form.html', 'trades/form.html'):
    html = text('templates/sourcing/' + name)
    if 'data-sourcing-page-draft' not in html or 'data-sourcing-company' not in html or 'sourcing-page-draft.js' not in html:
        raise SystemExit(f"SOURCING LOOKUP/DRAFT ERROR: {name} lacks form recovery")
print('PASS: bounded lookup pagination, quick-create discard and standalone form recovery contracts')
