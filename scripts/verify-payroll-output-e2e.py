#!/usr/bin/env python3
"""Static release gate for Payroll reports, WPS/payments and final documents."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-output-e2e.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL OUTPUT E2E ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def require(rel: str, marker: str) -> None:
    if marker not in text(rel):
        fail(f"{rel} missing required output contract marker: {marker}")


def methods(rel: str, function_name: str) -> set[str]:
    module = ast.parse(text(rel), filename=rel)
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != function_name:
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "require_GET":
                return {"GET"}
            if isinstance(decorator, ast.Name) and decorator.id == "require_POST":
                return {"POST"}
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "require_http_methods":
                return {str(item).upper() for item in ast.literal_eval(decorator.args[0])}
        return set()
    fail(f"backend function missing: {rel}:{function_name}")
    return set()


try:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"cannot read output contract: {exc}")

js = text("static/payroll/js/app.js")
reports = text("apps/core/management/reports.py")
seed = text("apps/core/management/commands/seed_payroll_test_data.py")
doc_service = text("apps/documents/services/documents.py")
doc_api = text("apps/documents/api.py")

# Reporting is server generated, has a real CSV endpoint, and the download matches the visible search filter.
for workspace, report_types in contract["reports"]["types"].items():
    for report_type in report_types:
        if f'"{report_type}"' not in reports and f"'{report_type}'" not in reports:
            fail(f"server report type missing for {workspace}: {report_type}")
        if f'"{report_type}"' not in seed and f"'{report_type}'" not in seed:
            fail(f"DEMO coverage missing for report: {report_type}")
for marker in (
    "function reportRequest()",
    "`/api/reports/?${params.toString()}`",
    "function exportCurrentReport()",
    "params.set('q',query)",
    "function printCurrentReport()",
    'query = request.GET.get("q", "").strip().casefold()',
):
    target = js if marker.startswith(("appApi", "function", "params", "`/api/")) else text("apps/core/management_api.py")
    if marker not in target:
        fail(f"report output marker missing: {marker}")
if methods("apps/core/management_api.py", "reports_api") != {"GET"}:
    fail("reports_api must remain GET-only")
if methods("apps/core/management_api.py", "report_export_api") != {"GET"}:
    fail("report_export_api must remain GET-only")

# Internal salary payment/WPS chain: readiness -> prepare -> export -> start -> reconcile -> retry -> close/reopen.
internal_methods = {
    "salary_payments_api": {"GET"},
    "prepare_salary_payment_batch_api": {"POST"},
    "salary_payment_batch_export_api": {"POST"},
    "salary_payment_batch_workflow_api": {"POST"},
    "salary_payment_results_api": {"POST"},
    "salary_payment_row_retry_api": {"POST"},
}
for fn in contract["internal_payment_flow"]:
    actual = methods("apps/internal_payroll/payment_api.py", fn)
    if not internal_methods[fn].issubset(actual):
        fail(f"Internal payment HTTP contract drift for {fn}: {sorted(actual)}")
for marker in (
    "data-wps-validate", "data-wps-prepare", "prepareWpsBatch",
    "data-payment-export", "importPaymentResults", "data-payment-retry",
    "data-payment-close-payroll", "data-payment-reopen-batch",
):
    if marker not in js:
        fail(f"Internal WPS/payment UI path missing: {marker}")

# Rental supplier settlement/payment chain and supplier-profile drill-down must be live, not placeholder navigation.
rental_expected = {
    "rental_settlements_api": {"GET"},
    "rental_settlements_calculate_api": {"POST"},
    "rental_settlements_workflow_api": {"POST"},
    "supplier_payments_api": {"GET", "POST"},
    "supplier_payment_result_api": {"POST"},
    "supplier_payment_retry_api": {"POST"},
}
for fn in contract["rental_payment_flow"]:
    actual = methods("apps/rental_manpower/api.py", fn)
    if not rental_expected[fn].issubset(actual):
        fail(f"Rental payment HTTP contract drift for {fn}: {sorted(actual)}")
for marker in (
    "data-open-supplier-payments", "state.paymentSupplierFilter=btn.dataset.openSupplierPayments",
    "data-supplier-payment-open", "data-settlement-progress", "data-settlement-close",
    "data-supplier-payment-new", "data-supplier-payment-retry",
):
    if marker not in js:
        fail(f"Rental settlement/payment drill-down missing: {marker}")
if "settlement detail will be fully interactive" in js.lower():
    fail("obsolete supplier-settlement placeholder toast returned")

# Final documents: all seven supported types must be server gated, seedable, list/detail/finalize/print capable.
for document_type in contract["document_types"]:
    marker = f"DocumentType.{document_type}"
    if marker not in doc_service:
        fail(f"document service type missing: {document_type}")
    if marker not in seed:
        fail(f"DEMO document coverage missing: {document_type}")
for fn, expected in {
    "documents_api": {"GET", "POST"},
    "document_sources_api": {"GET"},
    "document_detail_api": {"GET"},
}.items():
    actual = methods("apps/documents/api.py", fn)
    if not expected.issubset(actual):
        fail(f"document HTTP contract drift for {fn}: {sorted(actual)}")
for marker in (
    "data-document-generate", "openDocumentGenerateDrawer", "generateDocumentFromDrawer",
    "data-document-print", "printDocumentRecord", "data-open-supplier-documents",
    "doc.entityReference === supplier.code", "data-document-open",
):
    if marker not in js:
        fail(f"document frontend path missing: {marker}")
for marker in (
    "Salary payment receipts require a Paid salary-payment row.",
    "Rental timesheet documents require a Locked project timesheet.",
    "Settlement documents require an Approved or later supplier settlement.",
    "Supplier Payment Advice requires a Paid supplier payment.",
):
    if marker not in doc_service:
        fail(f"document finalization gate missing: {marker}")
require("apps/documents/views.py", "verify_document_snapshot(document)")
require("scripts/verify-full-demo-seed.py", "def _verify_report_coverage" if False else "Complete DEMO payroll/WPS/report/document")

print(
    "Verified Payroll output E2E contract: "
    f"{sum(len(v) for v in contract['reports']['types'].values())} report routes, "
    f"{len(contract['internal_payment_flow'])} internal payment/WPS endpoints, "
    f"{len(contract['rental_payment_flow'])} rental finance endpoints and "
    f"{len(contract['document_types'])} final document types."
)
