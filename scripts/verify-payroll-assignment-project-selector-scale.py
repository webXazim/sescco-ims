#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL ASSIGNMENT PROJECT SELECTOR ERROR: {message}")

def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

if text("VERSION").strip() != "1.0.114":
    fail("VERSION must be 1.0.114")
contract = json.loads(text("merge/payroll-assignment-project-selector-scale.json"))
if contract.get("release") != "1.0.114":
    fail("assignment-project selector contract release must be 1.0.114")
lookup = contract.get("server_lookup") or {}
for key, expected in {
    "minimum_query_chars": 2,
    "dropdown_page_size": 10,
    "max_results_per_request": 25,
    "exact_count_query": False,
    "active_projects_only": True,
    "effective_date_aware": True,
    "company_scoped": True,
    "transfer_excludes_current_project": True,
}.items():
    if lookup.get(key) != expected:
        fail(f"server lookup contract changed: {key}")

urls = text("apps/rental_manpower/urls.py")
api = text("apps/rental_manpower/api.py")
js = text("static/payroll/js/app.js")
tests = text("apps/rental_manpower/tests/test_assignment_project_lookup.py")

if 'api/rental/assignments/project-lookup/' not in urls or 'assignment_project_lookup_api' not in urls:
    fail("bounded assignment project lookup route is missing")
for needle in (
    "def assignment_project_lookup_api",
    "len(query) < 2",
    "page_size = min(25",
    "start + page_size + 1",
    "status=ProjectStatus.ACTIVE",
    "start_date__lte=effective_date",
    "end_date__gte=effective_date",
    "rows = rows.exclude(pk=excluded.pk)",
    '"hasNext": has_next',
):
    if needle not in api:
        fail(f"assignment lookup lost bounded/date-safe behavior: {needle}")
lookup_slice = api[api.index("def assignment_project_lookup_api"):api.index("def assignments_api")]
if 'Paginator(' in lookup_slice or 'count()' in lookup_slice or 'serialize_list(' in lookup_slice:
    fail("assignment lookup must remain count-free page_size+1 pagination")

for needle in (
    "function assignmentProjectLookupComboboxField",
    "function setupRentalAssignmentProjectLookup",
    "/api/rental/assignments/project-lookup/",
    "const pageSize=10",
    "assignmentProjectLookupController?.abort()",
    "Type at least 2 characters to search.",
    "Search project name, code, client or location",
    "exclude_project_id",
    "selectRow(null);search.value=''",
):
    if needle not in js:
        fail(f"search-inside-dropdown assignment selector lost behavior: {needle}")

transfer = js[js.index("if (action === 'transfer')"):js.index("} else if (action === 'trade')")]
assign = js[js.index("} else if (action === 'assign')"):js.index("} else if (action === 'cancel')")]
if "namedSelectOptions('Transfer to project'" in transfer or "namedSelectOptions('Project'" in assign:
    fail("assign/transfer drawers regressed to full project <select> rendering")
if "assignmentProjectLookupComboboxField" not in transfer or "assignmentProjectLookupComboboxField" not in assign:
    fail("assign/transfer drawers must use bounded searchable project dropdown")

save_block = js[js.index("if (action === 'transfer' || action === 'assign')"):js.index("} else if (action === 'trade')", js.index("if (action === 'transfer' || action === 'assign')"))]
if "state.projects.find" in save_block:
    fail("assignment save still requires the browser project-directory cache")
if "requestBody.project_id = projectId" not in save_block:
    fail("assignment save no longer posts the server-selected project id")

for method in (
    "test_lookup_requires_search_and_uses_bounded_count_free_pages",
    "test_lookup_caps_requested_page_size_at_twenty_five",
):
    if f"def {method}" not in tests:
        fail(f"missing Django regression: {method}")

print("Verified SESCCO MS 1.0.114 assignment project selector scale safety: embedded search, bounded count-free paging, date-valid active projects, current-project exclusion and no directory-cache save dependency.")
