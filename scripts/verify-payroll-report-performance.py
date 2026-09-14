#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL REPORT PERFORMANCE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", None) or node.lineno
            return "\n".join(lines[node.lineno - 1:end])
    fail(f"missing function: {name}")
    return ""


version = text("VERSION").strip()
if version != "1.0.82":
    fail(f"VERSION must be 1.0.82, found {version!r}")

contract = json.loads(text("merge/payroll-report-performance.json"))
if contract.get("release") != version:
    fail("report-performance contract release does not match VERSION")
if contract.get("predecessor", {}).get("release") != "1.0.77":
    fail("report-performance predecessor must remain 1.0.77")
if contract.get("predecessor", {}).get("sha256") != "e5b3b5830025cfe40775524fd28947ae423e0fec68c3e26d1cde2ad3338926c6":
    fail("1.0.77 predecessor SHA changed")
if set(contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("report page sizes must remain 25/50/100")
if contract.get("schema_change") is not False or contract.get("payroll_formula_change") is not False:
    fail("1.0.82 report hotfix must not change schema or Payroll formulas")

reports = text("apps/core/management/reports.py")
wps = function_source(reports, "_interactive_wps")
for needle in (
    ".values_list(",
    '"employee__employee_number"',
    '"employee__full_name"',
    '"destination_type"',
    '"bank_name"',
    '"bank_code"',
    '"wps_enabled"',
    '"iban_fingerprint"',
    '"salary_card_fingerprint"',
    'profiles=Count("id")',
    'wps_enabled=Count("id", filter=Q(wps_enabled=True))',
):
    if needle not in wps:
        fail(f"WPS report lost bounded projection/aggregate marker: {needle}")
for forbidden in (
    'select_related("employee")',
    '"iban",',
    '"salary_card_number",',
    "get_destination_type_display()",
):
    if forbidden in wps:
        fail(f"WPS interactive report reintroduced secret/model hydration: {forbidden}")

api = text("apps/core/management_api.py")
payload_fn = function_source(api, "_report_payload")
if 'include_periods = request.GET.get("include_periods", "1")' not in payload_fn:
    fail("reports API cannot skip repeated period-list queries")
if "if include_periods" not in payload_fn:
    fail("reports API period omission is not conditional")

js = text("static/payroll/js/app.js")
for needle in (
    "reportPeriods: []",
    "function renderReportsInPlace()",
    "function wireReportActions()",
    "include_periods','0'",
    "reportSearchTimer",
    'data-no-sort="true"',
    "setReportBusy(true)",
):
    if needle not in js:
        fail(f"report browser hotfix marker missing: {needle}")
wire = function_source(js, "wireReportActions") if False else ""
# app.js is JavaScript; verify the bounded report section textually instead of parsing it as Python.
start = js.find("function wireReportActions()")
end = js.find("function settingsInputRow", start)
if start < 0 or end < 0:
    fail("cannot isolate wireReportActions")
wire_js = js[start:end]
if "renderRoute()" in wire_js:
    fail("report interactions rebuild the full Payroll route/shell")
if "loadReportContext({render:true,force:true})" not in wire_js:
    fail("report interactions are not server-refreshing in place")

scale_report = text("apps/core/management/commands/payroll_browser_scale_report.py")
for needle in ("WPS report page (100)", "WPS report search (100)", 'report_type="wps"'):
    if needle not in scale_report:
        fail(f"runtime scale report does not benchmark the WPS report path: {needle}")

runner = text("scripts/certify-payroll-browser-scale.py")
for needle in ('[data-report-type="wps"]', 'record("reports", started, rows=rows, report_type="wps")'):
    if needle not in runner:
        fail(f"live browser certification does not exercise WPS Reports: {needle}")

regression = text("apps/core/tests/test_management_reporting.py")
for needle in (
    "test_interactive_wps_report_does_not_decrypt_payment_destinations",
    'patch("apps.core.encryption.decrypt_text"',
):
    if needle not in regression:
        fail(f"WPS no-decrypt runtime regression is missing: {needle}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh"):
    if "verify-payroll-report-performance.py" not in text(rel):
        fail(f"{rel} does not enforce the report-performance hotfix gate")

print("Verified SESCCO MS 1.0.82 report/WPS performance hotfix: projection-only WPS rows, in-place report refresh and explicit WPS scale certification.")
