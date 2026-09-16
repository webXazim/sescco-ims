#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL PAYMENT SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.113":
    fail(f"VERSION must be 1.0.113, found {version!r}")
contract = json.loads(text("merge/payroll-payment-scale.json"))
if contract.get("release") != version:
    fail("payment scale contract does not match VERSION")
readiness = contract.get("readiness_register") or {}
if readiness.get("page_sizes") != [25, 50, 100] or readiness.get("default_page_size") != 50:
    fail("readiness page-size contract changed")
if readiness.get("scan_chunk") != 250:
    fail("readiness scan chunk must remain 250")
rows_contract = contract.get("payment_batch_rows") or {}
if rows_contract.get("page_sizes") != [25, 50, 100] or rows_contract.get("rows_in_shell") is not False:
    fail("payment batch-row contract changed")
if (contract.get("mutation_contract") or {}).get("response") != "compact-delta":
    fail("payment mutations regressed from compact deltas")

selector = text("apps/internal_payroll/selectors/payment.py")
api = text("apps/internal_payroll/payment_api.py")
employee_api = text("apps/internal_payroll/api.py")
urls = text("apps/internal_payroll/urls.py")
js = text("static/payroll/js/app.js")
tests = text("apps/internal_payroll/tests/test_payment.py")
for rel, source in (
    ("apps/internal_payroll/selectors/payment.py", selector),
    ("apps/internal_payroll/payment_api.py", api),
    ("apps/internal_payroll/api.py", employee_api),
    ("apps/internal_payroll/tests/test_payment.py", tests),
):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        fail(f"{rel} is invalid Python: {exc}")

for needle in (
    "PAYMENT_PAGE_SIZES = {25, 50, 100}",
    "PAYMENT_READINESS_SCAN_CHUNK = 250",
    "def salary_payment_shell_context(",
    '"profilesDeferred": True',
    "serialize_payment_batch(item, membership=membership, include_rows=False)",
    "def salary_payment_readiness_page_context(",
    '"surface": "salary_payment_readiness_page"',
    "employee_ids=chunk_ids",
    "def salary_payment_batch_rows_context(",
    '"surface": "salary_payment_batch_rows_page"',
    'summary_qs.aggregate(value=Sum("amount"))',
):
    if needle not in selector:
        fail(f"bounded payment selector protection missing: {needle}")
serializer_start = selector.find("def serialize_payment_batch")
serializer_end = selector.find("def _serialize_readiness", serializer_start)
serializer_body = selector[serializer_start:serializer_end]
if "if include_rows:" not in serializer_body:
    fail("compact batch serializer no longer gates row queries behind include_rows")

for needle in (
    "salary_payment_shell_context(",
    "def salary_payment_readiness_api(",
    "salary_payment_readiness_page_context(",
    "def salary_payment_batch_rows_api(",
    "salary_payment_batch_rows_context(",
    '@require_http_methods(["GET", "PATCH", "DELETE"])',
    "include_rows=False",
):
    if needle not in api:
        fail(f"payment API cutover protection missing: {needle}")
for needle in (
    'api/internal/salary-payments/readiness/',
    'api/internal/salary-payments/batches/<uuid:batch_id>/rows/',
):
    if needle not in urls:
        fail(f"payment scale URL missing: {needle}")

employees_start = employee_api.find("def employees_api")
employees_end = employee_api.find("def employee_detail_api", employees_start)
employees_body = employee_api[employees_start:employees_end]
if "salary_payment_context" in employees_body:
    fail("employee WPS filter regressed to full salary_payment_context hydration")
if "payment_readiness(" not in employees_body:
    fail("employee WPS filter lost direct readiness classification")

for needle in (
    "bankReadinessPageSize: Number(localStorage.getItem('payroll-ui-bank-readiness-page-size') || 50)",
    "wpsPageSize: Number(localStorage.getItem('payroll-ui-wps-page-size') || 50)",
    "paymentPageSize: Number(localStorage.getItem('payroll-ui-payment-page-size') || 50)",
    "function paymentReadinessRequest(channel, period = state.period)",
    "function cancelPaymentReadinessRequest(channel)",
    "async function loadPaymentReadiness(channel, period = state.period",
    "function paymentBatchRowsRequest(batchId)",
    "function cancelPaymentBatchRowsRequest()",
    "async function loadPaymentBatchRows(batchId",
    "async function loadEmployeePaymentProfile(employeeId",
    "function invalidatePaymentScaleContexts()",
    "[data-bank-readiness-page]",
    "[data-wps-page]",
    "[data-payment-page]",
    "kind==='wps'?'wps':kind==='bank'?'bank-readiness':'payment'",
    "document.getElementById('bankReadinessPageSize')",
    "document.getElementById('wpsPageSize')",
    "document.getElementById('paymentPageSize')",
):
    if needle not in js:
        fail(f"payment browser-scale protection missing: {needle}")
if "Fetching payment profiles, templates and batch history." in js:
    fail("Bank/WPS shell still advertises eager profile hydration")

for name in (
    "test_salary_payment_shell_defers_profiles_readiness_and_batch_rows",
    "test_salary_payment_readiness_is_server_paginated_and_serializes_page_profiles_only",
    "test_salary_payment_batch_rows_are_server_paginated_with_exact_summary",
):
    if name not in tests:
        fail(f"Django regression missing: {name}")

print("Verified SESCCO MS 1.0.113 Salary Payments + Bank/WPS scale cutover: compact shell, bounded readiness/batch rows, lazy profiles and compact mutations.")
