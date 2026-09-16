#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL FINAL BROWSER CERTIFICATION ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.115":
    fail(f"VERSION must be 1.0.115, found {version!r}")

contract = json.loads(text("merge/payroll-final-browser-certification.json"))
if contract.get("release") != version:
    fail("final browser certification contract does not match VERSION")
if contract.get("benchmark_volume") != {"internal_employees": 2000, "rental_workers": 5000, "history_months": 12}:
    fail("final benchmark volume changed")
if set(contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("final page-size contract must remain 25/50/100")
if int(contract.get("max_rendered_business_rows") or 0) != 100:
    fail("final DOM business-row cap must remain 100")
if int(contract.get("max_assignment_expanded_rows") or 0) != 200:
    fail("assignment expanded-row cap must remain 200")
if int(contract.get("max_global_search_results") or 0) != 30:
    fail("global search cap must remain 30")
if int(contract.get("max_context_payload_bytes") or 0) > 2_500_000:
    fail("payload budget was loosened above 2.5 MB")
if contract.get("schema_change") is not False or contract.get("payroll_formula_change") is not False:
    fail("1.0.115 must not introduce schema or payroll-formula changes")

required_surfaces = {
    "internal-employee-directory",
    "internal-attendance",
    "internal-overtime",
    "salary-setup-employee-structures",
    "payroll-runs-register",
    "payroll-runs-review",
    "internal-advances-adjustments",
    "salary-payments-register",
    "bank-readiness",
    "wps-readiness",
    "documents",
    "reports",
    "archive",
    "delete-recovery",
    "management-approval-center",
    "management-audit-trail",
    "rental-workforce-directory",
    "rental-worker-adjustments",
    "rental-project-timesheets",
    "rental-overtime",
    "rental-assignment-activity",
    "rental-current-deployment",
    "rental-supplier-pool",
    "global-search",
}
if set(contract.get("certified_surfaces") or []) != required_surfaces:
    missing = sorted(required_surfaces - set(contract.get("certified_surfaces") or []))
    extra = sorted(set(contract.get("certified_surfaces") or []) - required_surfaces)
    fail(f"final certified surface set changed; missing={missing}, extra={extra}")

# All prior scale slices must be carried forward to the same release.
for rel in (
    "merge/payroll-browser-scale.json",
    "merge/payroll-employee-residual-scale.json",
    "merge/payroll-salary-setup-scale.json",
    "merge/payroll-run-scale.json",
    "merge/payroll-adjustment-scale.json",
    "merge/payroll-rental-adjustment-page-scale.json",
    "merge/payroll-payment-scale.json",
    "merge/payroll-shared-surfaces-scale.json",
):
    if json.loads(text(rel)).get("release") != version:
        fail(f"prior scale contract is not carried forward to {version}: {rel}")

js = text("static/payroll/js/app.js")
# These IDs are the real interactive controls used by the expanded Chromium certification.
for needle in (
    'id="employeeSearch"',
    'id="timesheetSearch"',
    'id="salaryStructureSearch"',
    'id="payrollSearch"',
    'id="adjustmentSearch"',
    'id="paymentSearch"',
    'id="bankExportSearch"',
    'id="wpsSearch"',
    'id="documentSearch"',
    'id="reportSearch"',
    'id="recordManagementSearch"',
    'id="managementAuditSearch"',
    'id="rentalAssignmentSearch"',
    'id="rentalTimesheetSearch"',
    'id="salaryStructurePageSize"',
    'id="payrollPageSize"',
    'id="documentPageSize"',
    'id="reportPageSize"',
    'id="managementApprovalPageSize"',
    'id="managementAuditPageSize"',
):
    if needle not in js:
        fail(f"final browser surface/control missing from Payroll UI: {needle}")

for needle in (
    "document.getElementById('paymentPageSize')",
    "document.getElementById('bankReadinessPageSize')",
    "document.getElementById('wpsPageSize')",
):
    if needle not in js:
        fail(f"dynamic payment pagination control missing from Payroll UI: {needle}")

template = text("templates/payroll/app.html")
if 'id="globalSearchInput"' not in template:
    fail("global Payroll search input is missing from the Payroll shell template")

# High-cardinality request families must retain explicit cancellation authority.
for needle in (
    "cancelServerDirectoryRequest",
    "cancelInternalAttendanceRequest",
    "cancelSalaryStructureRequest",
    "cancelPayrollRunRequest",
    "cancelInternalAdjustmentRequest",
    "cancelRentalAdjustmentRequest",
    "cancelPaymentBatchRowsRequest",
    "cancelPaymentReadinessRequest('bank_csv')",
    "cancelPaymentReadinessRequest('wps')",
    "cancelDocumentListRequest",
    "cancelReportRequest",
    "cancelRecordManagementRequest",
    "cancelManagementApprovalRequest",
    "cancelManagementAuditRequest",
    "cancelRentalAssignmentRequest",
    "cancelRentalTimesheetRequest",
):
    if needle not in js:
        fail(f"stale-request cancellation contract missing: {needle}")

# Final live runner must exercise every newly scaled tranche plus the inherited core paths.
runner = text("scripts/certify-payroll-browser-scale.py")
runner_needles = (
    '"internal-employees"',
    '"salary-setup"',
    '"payroll-runs"',
    '"adjustments"',
    '"payments"',
    '"bank-export"',
    '"wps"',
    '"documents"',
    '"reports"',
    '"archive"',
    '"trash"',
    '"management-approvals"',
    '"management-audit"',
    '"rental-assignments"',
    '"timesheets"',
    '#globalSearchInput',
    'rows > 100',
    'rows > 200',
)
for needle in runner_needles:
    if needle not in runner:
        fail(f"expanded live Chromium runner lost required coverage/bound: {needle}")
if '[data-report-type="wps"]' not in runner or 'report_type="wps"' not in runner:
    fail("live browser Reports certification does not explicitly exercise the WPS report variant")

try:
    ast.parse(runner)
except SyntaxError as exc:
    fail(f"live browser runner is invalid Python: {exc}")

report = text("apps/core/management/commands/payroll_browser_scale_report.py")
for needle in (
    "Payroll run page (100)",
    "Internal adjustment register (100)",
    "Rental worker adjustments page (100)",
    "Internal advance balances (100)",
    "Salary payment readiness / bank (100)",
    "Salary payment readiness / WPS (100)",
    "Documents page (100)",
    "Internal report page (100)",
    "WPS report page (100)",
    "WPS report search (100)",
    "Archive page (100)",
    "Delete recovery page (100)",
    "Management approvals page (100)",
    "Management audit page (100)",
):
    if needle not in report:
        fail(f"runtime scale report lost final surface measurement: {needle}")
try:
    ast.parse(report)
except SyntaxError as exc:
    fail(f"runtime scale report is invalid Python: {exc}")

# The final gate must be release-required, production-freeze-required and production-E2E-listed.
for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh"):
    if "verify-payroll-final-browser-certification.py" not in text(rel):
        fail(f"{rel} does not enforce the final browser certification gate")
production = json.loads(text("merge/payroll-production-e2e.json"))
if "scripts/verify-payroll-final-browser-certification.py" not in (production.get("static_verifiers") or []):
    fail("production E2E contract does not include the final browser certification verifier")
scenario_ids = {row.get("id") for row in production.get("scenarios") or []}
if "final-payroll-browser-certification" not in scenario_ids:
    fail("production E2E contract does not include final browser certification evidence")
labels = set(production.get("runtime_test_labels") or [])
if "apps.core.tests.test_payroll_final_browser_certification" not in labels:
    fail("production E2E labels do not include final browser certification regression test")

candidate = json.loads(text("merge/release-candidate.json"))
if "scripts/verify-payroll-final-browser-certification.py" not in (candidate.get("required_static_gates") or []):
    fail("release candidate does not require the final browser certification gate")
if not any("certify-payroll-browser-scale.py" in item for item in (candidate.get("required_benchmark_gates") or [])):
    fail("release candidate no longer requires live Chromium certification")

print("Verified SESCCO MS 1.0.115 final 2K/5K Payroll browser-certification freeze contract across 24 high-cardinality surfaces.")
