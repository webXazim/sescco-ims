#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"
TITLE = "1.0.116 — Sourcing HTTPS Test Transport Hotfix"
PREDECESSOR = "1.0.115-inventory-manager-permission-reconciliation-hotfix"
PREDECESSOR_SHA = "023a01ec01f2c9d9101dbfa56a9dc8e60f0b46748e3d10542f8477ad9d260438"


def fail(message: str) -> None:
    raise SystemExit(f"RELEASE CANDIDATE ERROR: {message}")


def text(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        fail(f"missing file: {rel}")
    return p.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(text("merge/release-candidate.json"))
if contract.get("release") != VERSION:
    fail("release-candidate version mismatch")
if contract.get("release_type") != "sourcing-https-test-transport-hotfix":
    fail("release type mismatch")
if contract.get("previous_release") != PREDECESSOR or contract.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("predecessor identity/checksum changed")
if contract.get("feature_freeze") is not True:
    fail("feature freeze must remain enabled")
if contract.get("schema_change_in_release") is not False:
    fail("test-transport hotfix must not claim a database schema change")
if contract.get("payroll_formula_change_in_release") is not False:
    fail("Payroll formulas must remain frozen")

required_static = set(contract.get("required_static_gates") or [])
required_now = {
    "scripts/verify-sourcing-https-test-transport-hotfix.py",
    "scripts/verify-inventory-manager-permission-reconciliation-hotfix.py",
    "scripts/verify-accounts-rental-supervisor-migration-hotfix.py",
    "scripts/verify-sourcing-migration-state-hotfix.py",
    "scripts/verify-index-name-hotfix.py",
    "scripts/verify-granular-access-authority.py",
    "scripts/verify-single-access-authority.py",
    "scripts/verify-inventory-storekeeper-scope.py",
    "scripts/verify-cross-module-access-leaks.py",
    "scripts/verify-sourcing-security-certification.py",
    "scripts/verify-payroll-production-e2e.py",
    "scripts/verify-production-infrastructure.sh",
}
if not required_now.issubset(required_static):
    fail(f"required static gates missing: {sorted(required_now-required_static)}")
for rel in required_static:
    if not (ROOT / rel).is_file():
        fail(f"registered static gate missing: {rel}")

runtime = set(contract.get("required_runtime_gates") or [])
for gate in (
    "python manage.py check --deploy --fail-level ERROR",
    "python manage.py makemigrations --check --dry-run",
    "python manage.py migrate --plan",
    "python manage.py merge_access_report --fail-on-errors",
    "python manage.py test --noinput",
):
    if gate not in runtime:
        fail(f"required runtime gate missing: {gate}")

if contract.get("inventory_manager_permission_reconciliation_migration") != "apps/accounts/migrations/0014_inventory_manager_import_permission.py":
    fail("reconciliation migration identity changed")
if contract.get("inventory_manager_permission_reconciliation_runtime_gate") != "python manage.py merge_access_report --fail-on-errors":
    fail("runtime reconciliation authority changed")

if not text("RELEASE_NOTES.md").startswith(f"# {TITLE}\n"):
    fail("release notes do not lead with current hotfix")
if f"SESCCO MS {TITLE}" not in text("README.md"):
    fail("README does not identify current packaged release")

for template, assets in {
    "templates/payroll/app.html": ("payroll/css/v2/payroll-controls.css", "payroll/js/app.js"),
    "templates/accounts/administration.html": ("platform/css/access-management.css", "platform/js/access-management.js"),
}.items():
    content = text(template)
    for asset in assets:
        if not re.search(re.escape(asset) + r"' %\}\?v=1\.0\.116", content):
            fail(f"asset cache buster not frozen at {VERSION}: {asset}")

# Key release-scoped authorities are carried forward; historical benchmark contracts
# that intentionally retain their original release are verified by their dedicated gates.
for rel in (
    "merge/sourcing-https-test-transport-hotfix.json",
    "merge/inventory-manager-permission-reconciliation-hotfix.json",
    "merge/accounts-rental-supervisor-migration-hotfix.json",
    "merge/sourcing-migration-state-hotfix.json",
    "merge/index-name-deployment-hotfix.json",
    "merge/granular-access-authority.json",
    "merge/single-access-authority.json",
    "merge/inventory-storekeeper-scope.json",
    "merge/sourcing-security-certification.json",
    "merge/sourcing-browser-e2e-production-freeze.json",
    "merge/payroll-production-e2e.json",
):
    if json.loads(text(rel)).get("release") != VERSION:
        fail(f"release-scoped contract not carried forward: {rel}")

for rel in (
    "apps/accounts/migrations/0013_rename_access_profile_index.py",
    "apps/accounts/migrations/0014_inventory_manager_import_permission.py",
    "apps/sourcing/migrations/0007_rename_manpower_contact_index.py",
    "apps/sourcing/migrations/0008_align_abstract_relation_state.py",
):
    if not (ROOT / rel).is_file():
        fail(f"required migration lineage missing: {rel}")

freeze = text("scripts/verify-production-freeze.sh")
release_tasks = text("scripts/release-tasks.sh")
for needle in (
    "verify-sourcing-https-test-transport-hotfix.py",
    "verify-inventory-manager-permission-reconciliation-hotfix.py",
    "verify-accounts-rental-supervisor-migration-hotfix.py",
    "verify-sourcing-security-certification.py",
    "verify-payroll-production-e2e.py",
):
    if needle not in freeze:
        fail(f"production freeze lost required verifier: {needle}")
    if needle not in release_tasks:
        fail(f"release tasks lost required verifier: {needle}")
if "merge_access_report --fail-on-errors" not in release_tasks:
    fail("release tasks no longer enforce access reconciliation")
if "scripts/verify-production-freeze.sh" not in text(contract["deployment_entrypoint"]):
    fail("canonical deployment no longer verifies packaged freeze")

print("Verified SESCCO MS 1.0.116 Sourcing HTTPS Test Transport Hotfix release contract.")
