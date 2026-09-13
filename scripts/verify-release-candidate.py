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
if version != "1.0.64":
    fail(f"VERSION must be 1.0.64, found {version!r}")

contract = json.loads(text("merge/release-candidate.json"))
if contract.get("release") != version:
    fail("release-candidate contract does not match VERSION")
if contract.get("previous_release") != "1.0.63":
    fail("release-candidate predecessor must remain 1.0.63")
if contract.get("previous_archive_sha256") != "8291351ac88c883796d899f31fbffbb32416b79f53e1ad8be1d3485fd0049d9e":
    fail("1.0.63 predecessor checksum changed")
if contract.get("feature_freeze") is not True:
    fail("final release must remain feature-frozen")
if contract.get("schema_change_in_release") is not False:
    fail("1.0.64 must not claim a schema change")
if contract.get("payroll_formula_change_in_release") is not False:
    fail("1.0.64 must not claim a Payroll formula change")
if set(contract.get("required_seed_profiles") or []) != {"functional", "realistic", "benchmark"}:
    fail("required seed profiles changed")

notes = text("RELEASE_NOTES.md")
if not notes.startswith("# 1.0.64 — Production freeze / release candidate\n"):
    fail("1.0.64 release notes must be the first release entry")
readme = text("README.md")
if "SESCCO MS 1.0.64 — Production freeze / release candidate" not in readme:
    fail("README does not identify the 1.0.64 packaged release")

payroll_template = text("templates/payroll/app.html")
for asset in ("payroll/css/v2/payroll-controls.css", "payroll/js/app.js"):
    pattern = re.escape(asset) + r"' %\}\?v=1\.0\.64"
    if not re.search(pattern, payroll_template):
        fail(f"Payroll asset cache buster is not frozen at 1.0.64 for {asset}")

production_e2e = json.loads(text("merge/payroll-production-e2e.json"))
if production_e2e.get("release") != "1.0.64":
    fail("Payroll production-E2E contract is not carried forward to 1.0.64")

freeze = text("scripts/verify-production-freeze.sh")
for rel in contract.get("required_static_gates") or []:
    if Path(rel).name not in freeze and rel not in freeze:
        fail(f"production freeze lost required static gate: {rel}")
if "verify-release-candidate.py" not in freeze:
    fail("production freeze does not verify the final release-candidate contract")

release_tasks = text("scripts/release-tasks.sh")
if "verify-release-candidate.py" not in release_tasks:
    fail("release tasks do not verify the final release-candidate contract")
if "verify-payroll-production-e2e.py" not in release_tasks:
    fail("release tasks lost Payroll production-E2E verification")

certify = text("scripts/certify-payroll-production-e2e.sh")
for needle in (
    "manage.py check --deploy --fail-level ERROR",
    "manage.py makemigrations --check --dry-run",
    'manage.py test "${TEST_LABELS[@]}" --noinput',
):
    if needle not in certify:
        fail(f"runtime Payroll certification lost required gate: {needle}")

rehearsal = text("scripts/rehearse-production-freeze.sh")
for needle in ("certify-payroll-production-e2e.sh", "payroll-e2e-certification.txt", "run_manage test --noinput"):
    if needle not in rehearsal:
        fail(f"production rehearsal lost runtime certification evidence: {needle}")

deploy = text(contract["deployment_entrypoint"])
if "scripts/verify-production-freeze.sh" not in deploy:
    fail("canonical production deployment no longer verifies the packaged freeze")

# Archive bytecode/cache hygiene is enforced at packaging time; running Python verifiers may create caches.

print("Verified SESCCO MS 1.0.64 production freeze / release-candidate contract.")
