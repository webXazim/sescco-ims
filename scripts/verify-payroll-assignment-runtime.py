#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL ASSIGNMENT RUNTIME ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.86":
    fail(f"VERSION must be 1.0.86, found {version!r}")

contract = json.loads(text("merge/payroll-assignment-runtime.json"))
if contract.get("release") != version:
    fail("assignment runtime contract does not match VERSION")
if contract.get("endpoint") != "/api/rental/assignments/":
    fail("assignment endpoint changed")
if set(contract.get("views") or []) != {"summary", "activity", "deployment", "pool"}:
    fail("assignment server views are incomplete")
if set(contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("assignment UI page-size contract changed")
if contract.get("search_debounce_ms") != 320:
    fail("assignment search debounce must remain 320 ms")

api = text("apps/rental_manpower/api.py")
selectors = text("apps/rental_manpower/selectors/assignments.py")
masters = text("apps/rental_manpower/selectors/masters.py")
js = text("static/payroll/js/app.js")
tests = text("apps/rental_manpower/tests/test_api.py")

for needle in (
    'if view == "summary":',
    'if view in {"deployment", "pool"}:',
    'if view == "activity":',
    'max_page_size=100',
    'operational_status="assigned" if view == "deployment" else "pool"',
    'Paginator(rows, controls.page_size)',
    'serialized_assignment_activity(company=request.company, assignments=segments, event_filter=event_type)',
):
    if needle not in api:
        fail(f"bounded assignment API protection missing: {needle}")

if 'def serialized_assignment_activity(' not in selectors:
    fail("bounded assignment activity serializer is missing")
if 'elif normalized == "pool":' not in masters:
    fail("supplier-pool server selector is missing")

for needle in (
    'rentalAssignmentServer: {',
    "activity:{results:[],meta:{}",
    "deployment:{results:[],meta:{}",
    "pool:{results:[],meta:{}",
    'const controller=new AbortController(),requestId=Number(store.requestId||0)+1;',
    "const payload=await appApi(request.url,{signal:controller.signal});",
    "if(error?.name==='AbortError')return store;",
    "serverRentalAssignmentView('activity')",
    "serverRentalAssignmentView('deployment')",
    "serverRentalAssignmentView('pool')",
    "serverRentalAssignmentView('summary')",
    'data-assignment-page=',
    'data-assignment-page-size=',
    "bindPayrollSearch(rentalAssignmentSearch,value=>{state.rentalAssignmentSearch=value;},{delay:320,beforeRender:()=>cancelRentalAssignmentRequest(state.rentalAssignmentTab)});",
    'invalidateRentalAssignmentServer();',
):
    if needle not in js:
        fail(f"assignment frontend runtime protection missing: {needle}")

start = js.find('  function rentalAssignmentsTemplate() {')
end = js.find('  function rentalWorkforceTemplate() {', start)
if start < 0 or end < 0:
    fail("could not locate Assignment Lifecycle route template")
route = js[start:end]
for forbidden in ('rentalAssignmentActivityRows()', 'rentalAssignmentIntegrity()', 'state.rentalWorkers.filter'):
    if forbidden in route:
        fail(f"Assignment Lifecycle returned to a full browser-side scan: {forbidden}")

if 'def test_assignment_lifecycle_views_are_server_paged(self):' not in tests:
    fail("Django regression coverage for paged Assignment Lifecycle views is missing")

print("Verified Rental Assignment Lifecycle server pagination: summary + Activity/Deployment/Pool bounded views, cancellation-aware search and no full-route workforce/history scan.")
