#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"RELEASE CANDIDATE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.70":
    fail(f"VERSION must be 1.0.70, found {version!r}")

contract = json.loads(text("merge/release-candidate.json"))
if contract.get("release") != version:
    fail("release-candidate contract does not match VERSION")
if contract.get("previous_release") != "1.0.69-postgresql-search-query-hardening":
    fail("1.0.70 predecessor must remain the 1.0.69 PostgreSQL query-hardening release")
if contract.get("previous_archive_sha256") != "04a1034fd4ae7b60dffd84991d13d4481fff5aa70d881a05ab39cff82d467c2a":
    fail("1.0.69 predecessor checksum changed")
if contract.get("feature_freeze") is not True:
    fail("1.0.70 must remain feature-frozen")
if contract.get("schema_change_in_release") is not False:
    fail("1.0.70 must not introduce another schema change")
if contract.get("schema_change_scope") != "none; carries forward the 1.0.69 PostgreSQL search indexes":
    fail("1.0.70 schema-change scope changed")
if contract.get("payroll_formula_change_in_release") is not False:
    fail("1.0.70 must not claim a Payroll formula change")
if set(contract.get("required_seed_profiles") or []) != {"functional", "realistic", "benchmark"}:
    fail("required seed profiles changed")
for required in ("scripts/verify-payroll-query-hardening.py", "scripts/verify-payroll-browser-scale.py"):
    if required not in (contract.get("required_static_gates") or []):
        fail(f"final scale freeze is missing required gate: {required}")
required_benchmark = set(contract.get("required_benchmark_gates") or [])
if not any("payroll_browser_scale_report" in item for item in required_benchmark):
    fail("benchmark-scale server report is not release-required")
if not any("certify-payroll-browser-scale.py" in item for item in required_benchmark):
    fail("live Chromium scale certification is not release-required")

notes = text("RELEASE_NOTES.md")
if not notes.startswith("# 1.0.70 — 5K/2K browser benchmark certification & production freeze\n"):
    fail("1.0.70 release notes must be the first release entry")
readme = text("README.md")
if "SESCCO MS 1.0.70 — 5K/2K browser benchmark certification & production freeze" not in readme:
    fail("README does not identify the 1.0.70 packaged release")

payroll_template = text("templates/payroll/app.html")
for asset in ("payroll/css/v2/payroll-controls.css", "payroll/js/app.js"):
    pattern = re.escape(asset) + r"' %\}\?v=1\.0\.70"
    if not re.search(pattern, payroll_template):
        fail(f"Payroll asset cache buster is not frozen at 1.0.70 for {asset}")

for rel in (
    "merge/payroll-production-e2e.json",
    "merge/payroll-directory-runtime.json",
    "merge/payroll-assignment-runtime.json",
    "merge/payroll-timesheet-scale.json",
    "merge/payroll-bootstrap-search.json",
    "merge/payroll-query-hardening.json",
    "merge/payroll-browser-scale.json",
):
    if json.loads(text(rel)).get("release") != "1.0.70":
        fail(f"release-scoped contract is not frozen at 1.0.70: {rel}")

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
for needle in ("#timesheetSearch", "#rentalAssignmentSearch", "#rentalTimesheetSearch", "#globalSearchInput"):
    if needle not in browser_certify:
        fail(f"live browser certification lost required surface: {needle}")

rehearsal = text("scripts/rehearse-production-freeze.sh")
for needle in ("certify-payroll-production-e2e.sh", "payroll-e2e-certification.txt", "run_manage test --noinput"):
    if needle not in rehearsal:
        fail(f"production rehearsal lost runtime certification evidence: {needle}")

deploy = text(contract["deployment_entrypoint"])
if "scripts/verify-production-freeze.sh" not in deploy:
    fail("canonical production deployment no longer verifies the packaged freeze")

print("Verified SESCCO MS 1.0.70 5K/2K browser benchmark certification/freeze contract.")
