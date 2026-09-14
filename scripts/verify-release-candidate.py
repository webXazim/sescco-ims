#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.78"
PREDECESSOR = "1.0.77-full-payroll-browser-certification-production-freeze"
PREDECESSOR_SHA256 = "e5b3b5830025cfe40775524fd28947ae423e0fec68c3e26d1cde2ad3338926c6"
TITLE = "1.0.78 — Reports/WPS performance hotfix"


def fail(message: str) -> None:
    raise SystemExit(f"RELEASE CANDIDATE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != VERSION:
    fail(f"VERSION must be {VERSION}, found {version!r}")

contract = json.loads(text("merge/release-candidate.json"))
if contract.get("release") != version:
    fail("release-candidate contract does not match VERSION")
if contract.get("release_type") != "reports-wps-performance-hotfix":
    fail("1.0.78 release type changed")
if contract.get("previous_release") != PREDECESSOR:
    fail("1.0.78 predecessor must remain the exact 1.0.77 browser-certification freeze")
if contract.get("previous_archive_sha256") != PREDECESSOR_SHA256:
    fail("1.0.77 predecessor checksum changed")
if contract.get("feature_freeze") is not True:
    fail("1.0.78 must remain feature-frozen")
if contract.get("schema_change_in_release") is not False:
    fail("1.0.78 must not introduce a schema change")
if contract.get("schema_change_scope") != "none; carries forward the 1.0.69 PostgreSQL search indexes":
    fail("1.0.78 schema-change scope changed")
if contract.get("payroll_formula_change_in_release") is not False:
    fail("1.0.78 must not claim a Payroll formula change")
if set(contract.get("required_seed_profiles") or []) != {"functional", "realistic", "benchmark"}:
    fail("required seed profiles changed")

scale_gates = (
    "scripts/verify-payroll-query-hardening.py",
    "scripts/verify-payroll-browser-scale.py",
    "scripts/verify-payroll-employee-residual-scale.py",
    "scripts/verify-payroll-salary-setup-scale.py",
    "scripts/verify-payroll-run-scale.py",
    "scripts/verify-payroll-adjustment-scale.py",
    "scripts/verify-payroll-payment-scale.py",
    "scripts/verify-payroll-shared-surfaces-scale.py",
    "scripts/verify-payroll-final-browser-certification.py",
    "scripts/verify-payroll-report-performance.py",
)
for required in scale_gates:
    if required not in (contract.get("required_static_gates") or []):
        fail(f"1.0.78 scale freeze is missing required gate: {required}")

required_benchmark = set(contract.get("required_benchmark_gates") or [])
if not any("payroll_browser_scale_report" in item for item in required_benchmark):
    fail("benchmark-scale server report is not release-required")
if not any("certify-payroll-browser-scale.py" in item for item in required_benchmark):
    fail("live Chromium scale certification is not release-required")

notes = text("RELEASE_NOTES.md")
if not notes.startswith(f"# {TITLE}\n"):
    fail("1.0.78 release notes must be the first release entry")
readme = text("README.md")
if f"SESCCO MS {TITLE}" not in readme:
    fail("README does not identify the 1.0.78 packaged release")

payroll_template = text("templates/payroll/app.html")
for asset in ("payroll/css/v2/payroll-controls.css", "payroll/js/app.js"):
    pattern = re.escape(asset) + r"' %\}\?v=1\.0\.78"
    if not re.search(pattern, payroll_template):
        fail(f"Payroll asset cache buster is not frozen at 1.0.78 for {asset}")

release_contracts = (
    "merge/payroll-production-e2e.json",
    "merge/payroll-directory-runtime.json",
    "merge/payroll-assignment-runtime.json",
    "merge/payroll-timesheet-scale.json",
    "merge/payroll-bootstrap-search.json",
    "merge/payroll-query-hardening.json",
    "merge/payroll-browser-scale.json",
    "merge/payroll-employee-residual-scale.json",
    "merge/payroll-salary-setup-scale.json",
    "merge/payroll-run-scale.json",
    "merge/payroll-adjustment-scale.json",
    "merge/payroll-payment-scale.json",
    "merge/payroll-shared-surfaces-scale.json",
    "merge/payroll-final-browser-certification.json",
    "merge/payroll-report-performance.json",
)
for rel in release_contracts:
    if json.loads(text(rel)).get("release") != VERSION:
        fail(f"release-scoped contract is not carried forward to {VERSION}: {rel}")

final_contract = json.loads(text("merge/payroll-final-browser-certification.json"))
if len(final_contract.get("certified_surfaces") or []) != 23:
    fail("final Payroll browser certification must cover exactly 23 high-cardinality surfaces")
if final_contract.get("benchmark_volume") != {"internal_employees": 2000, "rental_workers": 5000, "history_months": 12}:
    fail("final benchmark volume changed")
if set(final_contract.get("page_sizes") or []) != {25, 50, 100}:
    fail("final page-size contract changed")
if final_contract.get("max_rendered_business_rows") != 100 or final_contract.get("max_assignment_expanded_rows") != 200:
    fail("final DOM row budget changed")

freeze = text("scripts/verify-production-freeze.sh")
for rel in contract.get("required_static_gates") or []:
    if Path(rel).name not in freeze and rel not in freeze:
        fail(f"production freeze lost required static gate: {rel}")
if "verify-release-candidate.py" not in freeze:
    fail("production freeze does not verify the release-candidate contract")

release_tasks = text("scripts/release-tasks.sh")
for needle in (
    "verify-release-candidate.py",
    "verify-payroll-production-e2e.py",
    "verify-payroll-bootstrap-search.py",
    "verify-payroll-query-hardening.py",
    "verify-payroll-browser-scale.py",
    "verify-payroll-employee-residual-scale.py",
    "verify-payroll-salary-setup-scale.py",
    "verify-payroll-run-scale.py",
    "verify-payroll-adjustment-scale.py",
    "verify-payroll-payment-scale.py",
    "verify-payroll-shared-surfaces-scale.py",
    "verify-payroll-final-browser-certification.py",
    "verify-payroll-report-performance.py",
):
    if needle not in release_tasks:
        fail(f"release tasks lost required verification: {needle}")

certify = text("scripts/certify-payroll-production-e2e.sh")
for needle in (
    "manage.py check --deploy --fail-level ERROR",
    "manage.py makemigrations --check --dry-run",
    'manage.py test "${TEST_LABELS[@]}" --noinput',
):
    if needle not in certify:
        fail(f"runtime Payroll certification lost required gate: {needle}")

browser_certify = text("scripts/certify-payroll-browser-scale.py")
for needle in (
    "#employeeSearch", "#timesheetSearch", "#salaryStructureSearch", "#payrollSearch",
    "#adjustmentSearch", "#paymentSearch", "#bankExportSearch", "#wpsSearch",
    "#documentSearch", "#reportSearch", "#recordManagementSearch", "#managementAuditSearch",
    "#rentalAssignmentSearch", "#rentalTimesheetSearch", "#globalSearchInput",
    '"management-approvals"', '"management-audit"', '[data-report-type="wps"]',
):
    if needle not in browser_certify:
        fail(f"live browser certification lost required final surface: {needle}")

report = text("apps/core/management/commands/payroll_browser_scale_report.py")
for needle in (
    "Salary setup employee structures page (100)",
    "Payroll run page (100)",
    "Internal adjustment register (100)",
    "Salary payment readiness / bank (100)",
    "Documents page (100)",
    "Management audit page (100)",
    "WPS report page (100)",
    "WPS report search (100)",
):
    if needle not in report:
        fail(f"server benchmark report lost required final measurement: {needle}")

rehearsal = text("scripts/rehearse-production-freeze.sh")
for needle in ("certify-payroll-production-e2e.sh", "payroll-e2e-certification.txt", "run_manage test --noinput"):
    if needle not in rehearsal:
        fail(f"production rehearsal lost runtime certification evidence: {needle}")

deploy = text(contract["deployment_entrypoint"])
if "scripts/verify-production-freeze.sh" not in deploy:
    fail("canonical production deployment no longer verifies the packaged freeze")

print("Verified SESCCO MS 1.0.78 Reports/WPS performance hotfix release contract.")
