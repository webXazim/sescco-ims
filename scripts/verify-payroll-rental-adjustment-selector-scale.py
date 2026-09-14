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
if version != "1.0.82":
    fail(f"VERSION must be 1.0.82, found {version!r}")
contract = json.loads(text("merge/payroll-rental-adjustment-selector-scale.json"))
if contract.get("release") != version:
    fail("selector-scale contract release does not match VERSION")
if (contract.get("worker_lookup") or {}).get("max_results") != 25:
    fail("worker selector result cap must remain 25")
if (contract.get("worker_lookup") or {}).get("minimum_query_chars") != 2:
    fail("worker selector must remain search-gated at two characters")
if not (contract.get("project_lookup") or {}).get("effective_assignment_only"):
    fail("project selector must remain assignment-aware")

api = text("apps/rental_manpower/api.py")
urls = text("apps/rental_manpower/urls.py")
services = text("apps/rental_manpower/services/settlements.py")
js = text("static/payroll/js/app.js")
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
    "[:25]",
    "_has_effective_assignment=Exists(assignments)",
    "cancelled_at__isnull=True",
    "effective_from__lte=transaction_date",
    "project__status=ProjectStatus.ACTIVE",
    "project__deleted_at__isnull=True",
    'return JsonResponse({"ok": True, "results": [], "limit": 25, "requiresWorker": True})',
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
    "adjustmentPersonSearch",
    "adjustmentProjectSearch",
    "/api/rental/adjustments/lookup/?",
    "state.adjustmentPersonLookupController?.abort()",
    "state.adjustmentProjectLookupController?.abort()",
    "The selected worker has no eligible project assignment on the new transaction date.",
    "Search results are never loaded as a full directory.",
):
    if needle not in js:
        fail(f"drawer browser-safety protection missing: {needle}")

adjustments_start = js.find("  function adjustmentsTemplate() {")
adjustments_end = js.find("  function adjustmentFindRow", adjustments_start)
if adjustments_start < 0 or adjustments_end < 0:
    fail("could not locate rental adjustments renderer")
adjustments_body = js[adjustments_start:adjustments_end]
if "hydrateCompleteMaster('workers')" in adjustments_body:
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
    "test_project_lookup_is_restricted_to_effective_worker_assignment",
    "test_project_lookup_requires_worker_and_never_lists_global_project_master",
):
    if name not in tests:
        fail(f"Django regression missing: {name}")

print("Verified SESCCO MS 1.0.82 rental adjustment selector scale safety: bounded server search, assignment-aware projects, stale-request cancellation and no full-master hydration.")
