#!/usr/bin/env python3
"""Incremental Upgrade 05 source-contract verification, not runtime certification."""
from __future__ import annotations

import ast
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]

def source(name):
    path = root / name
    assert path.is_file(), f"missing {name}"
    content = path.read_text()
    if path.suffix == ".py":
        ast.parse(content, filename=name)
    return content

selector = source("apps/sourcing/selectors/service_finder.py")
views = source("apps/sourcing/views.py")
urls = source("apps/sourcing/urls.py")
access = source("apps/sourcing/access.py")
nav = source("templates/sourcing/sidebar.html")
page = source("templates/sourcing/subcontractors/_offers.html")
unified = source('templates/sourcing/subcontractors/list.html')
assert 'data-unified-form' in unified and 'data-unified-results' in unified and 'data-provider-expand' in unified
home = source("templates/sourcing/home.html")
profile = source("templates/sourcing/subcontractors/detail.html")
tests = source("apps/sourcing/tests/test_service_finder.py")

assert 'path("service-finder/", views.service_finder, name="service_finder")' in urls
assert 'def service_finder(request:' in views
assert '_require_subcontractor_view(request)' in views.split('def service_finder(request:', 1)[1].split('def workforce_finder(', 1)[0]
assert 'membership_can_manage_subcontractor_sourcing' in views
assert 'SOURCING_SUBCONTRACTORS_VIEW' in access
assert 'SOURCING_SUBCONTRACTORS_MANAGE' in access
assert "sourcing:subcontractor_list" in page
assert 'sourcing:subcontractor_list' in nav
assert 'subcontractor_list' in home
assert 'sourcing:subcontractor_list' in profile or 'sourcing:service_finder' in profile
assert '_legacy_finder_redirect(request, destination="sourcing:subcontractor_list")' in views
assert '_legacy_directory_query(request)' in views
for marker in (
    '.objects.for_company(company)',
    'is_active=True',
    'subcontractor__archived_at__isnull=True',
    'subcontractor__deleted_at__isnull=True',
    'subcontractor__status=SourcingEntityStatus.ACTIVE',
    'service__is_active=True',
    'select_related("service", "subcontractor", "verified_by")',
    'Paginator(qs, page_size)',
    'freshness_key(',
    'normalize_text(query)',
    'value.is_finite()',
):
    assert marker in selector, marker
for forbidden in ("apps.inventory", "apps.internal_payroll", "apps.rental_manpower", "apps.projects", "apps.accounting"):
    assert forbidden not in selector
for marker in ('data-sourcing-finder-root', 'data-sourcing-live-finder',
               'sourcing:subcontractor_service_history', 'sourcing:subcontractor_service_verify',
               'sourcing:subcontractor_service_edit', 'Rate expired', 'Not quoted'):
    assert marker in page, marker
assert re.search(r'{% if can_manage %}.*sourcing:subcontractor_service_verify', page, flags=re.S)
for marker in ('test_view_permission_and_editor_actions', 'test_company_and_lifecycle_isolation',
               'test_alias_scope_company_coverage_and_filters', 'test_freshness_policy_and_missing_or_expired_rates',
               'test_validated_input_sorting_and_bounded_pagination'):
    assert marker in tests
assert 'sourcing-finder-scale' in source('static/sourcing/js/finder-scale.js')

# Detect unbalanced template control flow without importing Django.
tokens = re.findall(r'{%\s*(.*?)\s*%}', page, re.S)
stack = []
pairs = {"endif": "if", "endfor": "for", "endblock": "block"}
for token in tokens:
    head = token.split()[0]
    if head in ("if", "for", "block"):
        stack.append(head)
    elif head in pairs:
        assert stack and stack.pop() == pairs[head], (head, stack)
    elif head in ("else", "elif"):
        assert stack and stack[-1] == "if", (head, stack)
    elif head == "empty":
        assert stack and stack[-1] == "for", (head, stack)
    else:
        assert head in ("url", "load", "extends", "static"), head
assert not stack, stack
print('PASS: Upgrade 05 Service Finder read-only source contract, routes, tenant scope, RBAC, bounded query, UI, and Django test structure.')
