#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"RENTAL ADJUSTMENT SELECTOR SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

version = text("VERSION").strip()
if version != "1.0.112":
    fail(f"VERSION must be 1.0.112, found {version!r}")
contract = json.loads(text("merge/payroll-rental-adjustment-selector-scale.json"))
if contract.get("release") != version:
    fail("selector-scale contract release does not match VERSION")
worker = contract.get("worker_lookup") or {}
project = contract.get("project_lookup") or {}
browser = contract.get("browser_safety") or {}
if worker.get("max_results") != 25 or worker.get("dropdown_page_size") != 10:
    fail("worker lookup must stay capped at 25 with 10-row dropdown pages")
if worker.get("minimum_query_chars") != 2:
    fail("worker selector must remain search-gated at two characters")
if worker.get("exact_count_query") is not False:
    fail("dropdown lookup must not require an exact count query")
if not worker.get("paginated_inside_dropdown") or not project.get("paginated_inside_dropdown"):
    fail("worker/project lookup pagination must remain inside the dropdown")
if not project.get("effective_assignment_only") or not project.get("exact_selected_project_revalidation"):
    fail("project selector must remain assignment-aware and exactly revalidatable")
if not browser.get("search_input_inside_dropdown") or browser.get("separate_find_fields") is not False:
    fail("search must remain inside the selector dropdown without duplicate Find fields")
if browser.get("persistent_feature_hints_below_lookup_fields") is not False:
    fail("lookup fields must not render persistent feature-explanation hints")
if browser.get("selected_project_metadata_below_field") is not False:
    fail("selected project metadata must stay inside the dropdown, not below the field")
if not browser.get("lookup_messages_inside_dropdown") or not browser.get("aligned_two_column_control_rows"):
    fail("lookup search/validation messaging must stay inside the dropdown so form rows remain aligned")

api = text("apps/rental_manpower/api.py")
urls = text("apps/rental_manpower/urls.py")
services = text("apps/rental_manpower/services/settlements.py")
js = text("static/payroll/js/app.js")
css = text("static/payroll/css/v2/payroll-controls.css")
tests = text("apps/rental_manpower/tests/test_api.py")
for rel, source in (("apps/rental_manpower/api.py", api), ("apps/rental_manpower/tests/test_api.py", tests)):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "def rental_adjustment_lookup_api(request: HttpRequest)",
    'mode not in {"workers", "projects"}',
    "len(query) < 2",
    "page_size = min(25, max(5",
    "page_size + 1",
    '"hasNext": has_next',
    '"hasPrevious": page > 1',
    "_has_effective_assignment=Exists(assignments)",
    "cancelled_at__isnull=True",
    "effective_from__lte=transaction_date",
    "project__status=ProjectStatus.ACTIVE",
    "project__deleted_at__isnull=True",
    'project = _scoped_project(request, project_id)',
):
    if needle not in api:
        fail(f"bounded lookup API protection missing: {needle}")

if 'path("api/rental/adjustments/lookup/", api.rental_adjustment_lookup_api' not in urls:
    fail("rental adjustment lookup URL is missing")

for needle in (
    "def _assignment_on_date",
    "Worker has no effective assignment to this project on the transaction date.",
    "rental_project_for_company(company=company, identifier=project_id, for_update=True, require_active=True)",
):
    if needle not in services:
        fail(f"transactional save authority missing: {needle}")

for needle in (
    "adjustmentLookupComboboxField",
    'data-adjustment-combobox-search',
    'data-adjustment-combobox-prev',
    'data-adjustment-combobox-next',
    "const pageSize=10",
    "/api/rental/adjustments/lookup/?",
    "state.adjustmentPersonLookupController?.abort()",
    "state.adjustmentProjectLookupController?.abort()",
    "The selected worker has no eligible project assignment on the new transaction date.",
):
    if needle not in js:
        fail(f"drawer combobox safety protection missing: {needle}")
for forbidden in ('>Find worker<', '>Find project<', 'id="adjustmentPersonSearch"', 'id="adjustmentProjectHint"', 'Search is inside this dropdown. Results are server-backed', 'Only assignment-valid active projects for the effective date are available.'):
    if forbidden in js:
        fail(f"duplicate external search UI returned: {forbidden}")
for needle in (
    ".adjustment-combobox__menu",
    ".adjustment-combobox__search",
    ".adjustment-combobox__results",
    ".adjustment-combobox__pager",
    "overscroll-behavior: contain",
):
    if needle not in css:
        fail(f"combobox production styling missing: {needle}")

adjustments_start = js.find("  function adjustmentsTemplate() {")
adjustments_end = js.find("  function adjustmentFindRow", adjustments_start)
if adjustments_start < 0 or adjustments_end < 0:
    fail("could not locate rental adjustments renderer")
if "hydrateCompleteMaster('workers')" in js[adjustments_start:adjustments_end]:
    fail("Rental Adjustments regressed to complete worker-master hydration")

save_start = js.find("    if (state.drawerType === 'advance') {")
save_end = js.find("    if (state.drawerType === 'rental-assignment-action')", save_start)
if save_start < 0 or save_end < 0:
    fail("could not locate adjustment save path")
save_body = js[save_start:save_end]
if "rentalWorkerById(personId)" in save_body or "state.projects.find(item=>item.id===projectId)" in save_body:
    fail("rental adjustment save regressed to browser directory-cache authority")

for name in (
    "test_worker_lookup_is_search_gated_and_assignment_aware",
    "test_worker_lookup_supports_bounded_in_dropdown_pagination",
    "test_project_lookup_is_restricted_to_effective_worker_assignment",
    "test_project_lookup_requires_worker_and_never_lists_global_project_master",
):
    if name not in tests:
        fail(f"Django regression missing: {name}")

print("Verified SESCCO MS 1.0.112 rental adjustment selector UX/scale safety: embedded search, bounded dropdown paging, clean aligned fields, assignment-aware projects and no full-master hydration.")
