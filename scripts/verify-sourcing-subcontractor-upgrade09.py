#!/usr/bin/env python3
"""Upgrade 09 source-only UI and isolation contracts; runtime tests need staging."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(name):
    return (ROOT / name).read_text(encoding="utf-8")

base = read("templates/sourcing/base.html")
assert "sourcing/css/refinement.css" in base
assert 'id="sourcing-main-content"' in base
assert 'class="sourcing-skip-link"' in base

list_page = read("templates/sourcing/subcontractors/list.html")
for text in ("subcontractor-sort", "subcontractor-direction", "active_service_type_count", "data-unified-results", "data-column=\"tags\"", "SOURCING_ACCESS.export", "{% if can_manage %}", "aria-label=\"Subcontractors table"):
    assert text in list_page, text

selector = read("apps/sourcing/selectors/subcontractors.py")
# The integrated directory keeps service counts tenant-scoped through a bounded
# correlated Subquery, avoiding high-cardinality joins and DISTINCT fanout.
for text in ("SourcingSubcontractorService.objects.for_company(company)",
             "service_qs.filter(is_active=True, service__is_active=True)",
             "active_service_type_count=Coalesce(Subquery(distinct_services",
             "service_hit=Exists(service_qs.filter("):
    assert text in selector, text
assert "for_company(company)" in selector
ast.parse(selector)

profile = read("templates/sourcing/subcontractors/detail.html")
for text in ('id="company-information"', 'id="service-catalog"', 'id="contacts"', 'id="activity"', 'id="lifecycle"', 'href="#qualifications"'):
    assert text in profile
assert "{% if can_manage %}<a href=\"#lifecycle\"" in profile
assert 'id="qualifications"' in read("templates/sourcing/subcontractors/_qualifications.html")

finder = read("templates/sourcing/subcontractors/_offers.html")
assert "data-sourcing-finder-root" in finder and "data-sourcing-live-finder" in finder
assert "sourcing-finder-filters" in finder
assert "data-unified-export" in list_page
exchange = read("templates/sourcing/data_exchange.html")
assert "sourcing-u09-exchange-guide" in exchange
assert "{% if import_choices %}" in exchange and "{% if export_choices %}" in exchange
assert "{% csrf_token %}" in exchange

css = read("static/sourcing/css/refinement.css")
assert '@media (max-width: 640px)' in css
assert ':focus-visible' in css
assert '.sourcing-shell-u09' in css

# No mutation of vendor/manpower HTML, access catalog or old shared stylesheet.
for forbidden in ("apps.inventory", "apps.projects", "apps.rental_manpower", "apps.internal_payroll"):
    assert forbidden not in selector

tests = read("apps/sourcing/tests/test_subcontractor_directory.py")
assert "test_directory_service_counts_are_active_and_company_scoped" in tests
assert "test_subcontractor_profile_section_navigation_respects_view_permissions" in tests
ast.parse(tests)
print("PASS: Upgrade 09 responsive UI, keyboard/table access, sort controls, service counts, permissions and regression contracts (source only).")
