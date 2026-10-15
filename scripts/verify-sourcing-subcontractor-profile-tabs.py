#!/usr/bin/env python3
"""Static release contract: Subcontractor tabs match Vendor/Manpower behavior."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
profile = (root / 'templates/sourcing/subcontractors/detail.html').read_text()
tabs = (root / 'static/sourcing/js/subcontractor-profile-tabs.js').read_text()
assert profile.count('data-subcontractor-tabs') == 1
for key in ('company-information', 'service-catalog', 'qualifications', 'contacts', 'activity', 'lifecycle'):
    assert f'data-sourcing-tab="{key}"' in profile, key
    assert f'data-sourcing-panel="{key}"' in profile, key
assert '{% if can_manage %}<button' in profile
assert 'data-sourcing-tab="lifecycle"' in profile
assert '{% if can_manage %}<section data-sourcing-panel="lifecycle"' in profile
assert 'id="service-catalog"' in profile and 'id="qualifications"' in (root / 'templates/sourcing/subcontractors/_qualifications.html').read_text()
assert profile.count('subcontractor-profile-tabs.js') == 1
assert profile.count('subcontractor-profile-tabs.css') == 1
css=(root / 'static/sourcing/css/subcontractor-profile-tabs.css').read_text()
assert 'overflow-x: auto' in css and '[hidden]' in css
assert len(re.findall(r'{%\s*block\s+scripts\s*%}', profile)) == 1
for contract in ('aria-selected', 'tabIndex', 'panel.hidden', 'hashchange', 'popstate', 'ArrowRight', 'ArrowLeft', 'Home', 'End', 'requestAnimationFrame'):
    assert contract in tabs, contract
assert 'data-sourcing-tab' in (root / 'templates/sourcing/vendors/detail.html').read_text()
assert 'data-sourcing-tab' in (root / 'templates/sourcing/manpower/detail.html').read_text()
print('PASS: Subcontractor profile has permission-gated keyboard accessible single-panel tabs and legacy deep-link support.')
