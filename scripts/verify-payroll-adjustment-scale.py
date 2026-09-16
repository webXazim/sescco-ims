#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL ADJUSTMENT SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

version = text("VERSION").strip()
if version != "1.0.111":
    fail(f"VERSION must be 1.0.111, found {version!r}")
contract = json.loads(text("merge/payroll-adjustment-scale.json"))
if contract.get("release") != version:
    fail("adjustment scale contract does not match VERSION")
register = contract.get("adjustment_register") or {}
if register.get("page_sizes") != [25, 50, 100] or register.get("default_page_size") != 50:
    fail("adjustment page-size contract changed")
if register.get("employee_lookup_max_results") != 25:
    fail("adjustment employee lookup must remain capped at 25")
if (contract.get("advance_balances") or {}).get("aggregation_authority") != "postgresql":
    fail("advance balances must remain database-aggregated")
if (contract.get("mutation_contract") or {}).get("response") != "single-adjustment-delta":
    fail("adjustment mutations regressed to full-context responses")

selector = text("apps/internal_payroll/selectors/payroll.py")
api = text("apps/internal_payroll/payroll_api.py")
profile = text("apps/internal_payroll/selectors/employee_profile.py")
js = text("static/payroll/js/app.js")
tests = text("apps/internal_payroll/tests/test_payroll_api.py")
for rel, source in (
    ("apps/internal_payroll/selectors/payroll.py", selector),
    ("apps/internal_payroll/payroll_api.py", api),
    ("apps/internal_payroll/selectors/employee_profile.py", profile),
    ("apps/internal_payroll/tests/test_payroll_api.py", tests),
):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "ADJUSTMENT_PAGE_SIZES = {25, 50, 100}",
    "def payroll_adjustment_page_context(",
    '"surface": "adjustments_page"',
    "def _advance_balance_queryset(",
    '.values("employee_id", "employee__employee_number", "employee__full_name")',
    '.annotate(balance=F("issued") - F("recovered"))',
    'employee_id__in=employee_ids',
    '.distinct("employee_id")',
    '"balanceSummary": balance_summary',
):
    if needle not in selector:
        fail(f"bounded adjustment selector protection missing: {needle}")

for needle in (
    "payroll_adjustment_page_context(",
    'page=request.GET.get("page", 1)',
    'page_size=request.GET.get("page_size", 50)',
    'search=str(request.GET.get("search") or "")',
    '"adjustment": serialize_payroll_adjustment(adjustment)',
):
    if needle not in api:
        fail(f"adjustment API cutover protection missing: {needle}")

adjustment_api_start = api.find("def payroll_adjustments_api")
adjustment_api_end = api.find("def payroll_adjustment_detail_api", adjustment_api_start)
if adjustment_api_start < 0 or adjustment_api_end < 0:
    fail("could not locate adjustment API")
mutation_body = api[adjustment_api_start:]
if "**payroll_period_context(" in mutation_body:
    fail("adjustment mutation responses regressed to the full payroll period context")

for needle in (
    '"adjustments": _period_adjustments(company=company, employee=employee, period_start=period_start)',
    '.filter(employee=employee, period_start=period_start)',
):
    if needle not in profile:
        fail(f"employee-profile adjustment scope missing: {needle}")

for needle in (
    "adjustmentPage: 1",
    "payroll-ui-adjustment-page-size",
    "adjustmentServer: { key:'', pendingKey:'', controller:null, requestId:0, loading:false, error:'', meta:{} }",
    "function internalAdjustmentRequest(period = state.period)",
    "function cancelInternalAdjustmentRequest()",
    "async function loadInternalAdjustmentPage(period = state.period",
    "data-adjustment-page=",
    'id="adjustmentPageSize"',
    "adjustmentLookupComboboxField",
    "page_size:String(pageSize)",
    "await refreshInternalAdjustmentAuthority",
):
    if needle not in js:
        fail(f"adjustment browser-scale protection missing: {needle}")

adjustments_start = js.find("  function adjustmentsTemplate() {")
adjustments_end = js.find("  function adjustmentFindRow", adjustments_start)
if adjustments_start < 0 or adjustments_end < 0:
    fail("could not locate adjustments renderer")
adjustments_body = js[adjustments_start:adjustments_end]
if "hydrateCompleteMaster('employees')" in adjustments_body:
    fail("Internal Adjustments regressed to complete employee-master hydration")
if "loadInternalPayrollPeriod(state.period)" in adjustments_body:
    fail("Internal Adjustments regressed to full payroll-period hydration")

for name in (
    "test_adjustment_register_is_server_paginated_with_exact_period_summary",
    "test_advance_balance_view_aggregates_in_database_and_pages_people",
    "test_adjustment_mutation_response_is_delta_not_full_payroll_context",
):
    if name not in tests:
        fail(f"Django regression missing: {name}")

print("Verified SESCCO MS 1.0.111 Advances & Adjustments scale cutover: bounded register/balances, server lookup/totals and delta mutations.")
