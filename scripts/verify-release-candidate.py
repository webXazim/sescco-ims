#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.114"
PREDECESSOR = "1.0.113-sourcing-migration-state-drift-hotfix"
PREDECESSOR_SHA256 = "aa870514601cb796a1f58bd569acd0c527082c411494b07dbcba830ba25a6a41"
TITLE = "1.0.114 — Accounts Rental Supervisor Migration Hotfix"


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
if contract.get("release") != VERSION:
    fail("release-candidate contract does not match VERSION")
if contract.get("release_type") != "accounts-rental-supervisor-migration-hotfix":
    fail("1.0.114 release type must be accounts-rental-supervisor-migration-hotfix")
if contract.get("previous_release") != PREDECESSOR or contract.get("previous_archive_sha256") != PREDECESSOR_SHA256:
    fail("1.0.114 predecessor identity/checksum changed")
if contract.get("feature_freeze") is not True:
    fail("1.0.114 packaged feature set must remain frozen")
if contract.get("schema_change_in_release") is not False:
    fail("1.0.114 must not claim a new schema migration")
expected_scope = "Deployment hotfix only: correct historical accounts.0008 RunPython model lookup from nonexistent accounts.Company to core.Company and pin migration-time ORM operations to schema_editor.connection.alias; no model/schema, data-design, Payroll formula, Inventory quantity, permission-catalog, Sourcing business-rule or operational integration change"
if contract.get("schema_change_scope") != expected_scope:
    fail("1.0.114 hotfix scope changed")
if contract.get("payroll_formula_change_in_release") is not False or contract.get("inventory_quantity_formula_change_in_release") is not False:
    fail("1.0.114 must not change Payroll or Inventory formulas")
if set(contract.get("required_seed_profiles") or []) != {"functional", "realistic", "benchmark"}:
    fail("required seed profiles changed")

required_gates = {
    "scripts/verify-accounts-rental-supervisor-migration-hotfix.py",
    "scripts/verify-sourcing-migration-state-hotfix.py",
    "scripts/verify-index-name-hotfix.py",
    "scripts/verify-granular-access-authority.py",
    "scripts/verify-single-access-authority.py",
    "scripts/verify-user-management-backend.py",
    "scripts/verify-user-management-ui.py",
    "scripts/verify-rental-supervisor-scope.py",
    "scripts/verify-inventory-storekeeper-scope.py",
    "scripts/verify-page-level-view-only.py",
    "scripts/verify-internal-finance-permissions.py",
    "scripts/verify-cross-module-access-leaks.py",
    "scripts/verify-credential-session-revocation.py",
    "scripts/verify-access-history-recovery.py",
    "scripts/verify-sourcing-domain-foundation.py",
    "scripts/verify-sourcing-access-control.py",
    "scripts/verify-sourcing-vendor-master.py",
    "scripts/verify-sourcing-material-catalog.py",
    "scripts/verify-sourcing-material-finder.py",
    "scripts/verify-sourcing-vendor-verification.py",
    "scripts/verify-sourcing-manpower-master.py",
    "scripts/verify-sourcing-trade-workforce-catalog.py",
    "scripts/verify-sourcing-workforce-finder.py",
    "scripts/verify-sourcing-data-exchange.py",
    "scripts/verify-sourcing-scale-hardening.py",
    "scripts/verify-sourcing-security-certification.py",
    "scripts/verify-sourcing-browser-e2e.py",
    "scripts/verify-payroll-query-hardening.py",
    "scripts/verify-payroll-browser-scale.py",
    "scripts/verify-payroll-salary-setup-scale.py",
    "scripts/verify-payroll-run-scale.py",
    "scripts/verify-payroll-adjustment-scale.py",
    "scripts/verify-payroll-payment-scale.py",
    "scripts/verify-payroll-shared-surfaces-scale.py",
    "scripts/verify-payroll-final-browser-certification.py",
    "scripts/verify-payroll-document-production.py",
    "scripts/verify-payroll-document-finalization-context.py",
}
registered=set(contract.get("required_static_gates") or [])
if not required_gates.issubset(registered):
    fail(f"release static gates incomplete: {sorted(required_gates-registered)}")
runtime=set(contract.get("required_runtime_gates") or [])
for gate in (
    "python manage.py merge_access_report --fail-on-errors",
    "python manage.py test apps.sourcing.tests.test_domain_foundation --noinput",
    "python manage.py test apps.sourcing.tests.test_access_control --noinput",
    "python manage.py test apps.sourcing.tests.test_vendor_master --noinput",
    "python manage.py test apps.sourcing.tests.test_material_catalog --noinput",
    "python manage.py test apps.sourcing.tests.test_material_finder --noinput",
    "python manage.py test apps.sourcing.tests.test_vendor_verification --noinput",
    "python manage.py test apps.sourcing.tests.test_manpower_master --noinput",
    "python manage.py test apps.sourcing.tests.test_trade_workforce_catalog --noinput",
    "python manage.py test apps.sourcing.tests.test_workforce_finder --noinput",
    "python manage.py test apps.sourcing.tests.test_data_exchange --noinput",
    "python manage.py test apps.sourcing.tests.test_scale_hardening --noinput",
    "python manage.py test apps.sourcing.tests.test_security_certification --noinput",
    "python manage.py test apps.sourcing.tests.test_browser_e2e_freeze --noinput",
):
    if gate not in runtime:
        fail(f"required runtime gate missing: {gate}")

notes=text("RELEASE_NOTES.md")
if not notes.startswith(f"# {TITLE}\n"):
    fail("1.0.114 release notes must be the first release entry")
readme=text("README.md")
if f"SESCCO MS {TITLE}" not in readme:
    fail("README does not identify the 1.0.114 packaged release")

for template, assets in {
    "templates/payroll/app.html": ("payroll/css/v2/payroll-controls.css", "payroll/js/app.js"),
    "templates/accounts/administration.html": ("platform/css/access-management.css", "platform/js/access-management.js"),
}.items():
    content=text(template)
    for asset in assets:
        pattern=re.escape(asset)+r"' %\}\?v=1\.0\.114"
        if not re.search(pattern,content):
            fail(f"asset cache buster is not frozen at 1.0.114 for {asset}")

release_contracts=(
    "merge/accounts-rental-supervisor-migration-hotfix.json",
    "merge/sourcing-migration-state-hotfix.json",
    "merge/index-name-deployment-hotfix.json",
    "merge/payroll-production-e2e.json","merge/payroll-directory-runtime.json","merge/payroll-assignment-runtime.json",
    "merge/payroll-timesheet-scale.json","merge/payroll-bootstrap-search.json","merge/payroll-query-hardening.json",
    "merge/payroll-browser-scale.json","merge/payroll-employee-residual-scale.json","merge/payroll-salary-setup-scale.json",
    "merge/payroll-run-scale.json","merge/payroll-adjustment-scale.json","merge/payroll-assignment-project-selector-scale.json",
    "merge/payroll-drawer-selector-scale.json","merge/payroll-rental-adjustment-selector-scale.json","merge/payroll-rental-adjustment-page-scale.json",
    "merge/payroll-payment-scale.json","merge/payroll-shared-surfaces-scale.json","merge/payroll-final-browser-certification.json",
    "merge/payroll-report-performance.json","merge/payroll-document-production.json","merge/payroll-document-finalization-context.json",
    "merge/granular-access-authority.json","merge/single-access-authority.json","merge/user-management-backend.json",
    "merge/user-management-ui.json","merge/rental-supervisor-scope.json","merge/inventory-storekeeper-scope.json",
    "merge/page-level-view-only.json","merge/internal-finance-permission-decomposition.json","merge/cross-module-access-leak-closure.json",
    "merge/credential-session-revocation-hardening.json","merge/access-history-recovery.json","merge/sourcing-domain-foundation.json",
    "merge/sourcing-access-control.json","merge/sourcing-vendor-master.json","merge/sourcing-material-catalog.json",
    "merge/sourcing-material-finder.json","merge/sourcing-vendor-verification.json","merge/sourcing-manpower-master.json",
    "merge/sourcing-trade-workforce-catalog.json",
    "merge/sourcing-workforce-finder.json",
    "merge/sourcing-data-exchange.json",
    "merge/sourcing-scale-hardening.json",
    "merge/sourcing-security-certification.json",
    "merge/sourcing-browser-e2e-production-freeze.json",
)
for rel in release_contracts:
    if json.loads(text(rel)).get("release") != VERSION:
        fail(f"release-scoped contract is not carried forward to {VERSION}: {rel}")

for rel in (
    "apps/core/migrations/0006_sourcing_audit_area.py",
    "apps/sourcing/migrations/0001_sourcing_domain_foundation.py",
    "apps/accounts/migrations/0012_sourcing_access_control_authority.py",
    "apps/sourcing/migrations/0002_vendor_directory_master.py",
    "apps/sourcing/migrations/0003_material_alias_search.py",
    "apps/sourcing/migrations/0004_manpower_supplier_contacts.py",
    "apps/sourcing/migrations/0005_trade_alias_search.py",
    "apps/sourcing/migrations/0006_scale_finder_indexes.py",
    "apps/accounts/migrations/0013_rename_access_profile_index.py",
    "apps/sourcing/migrations/0007_rename_manpower_contact_index.py",
    "apps/sourcing/migrations/0008_align_abstract_relation_state.py",
):
    if not (ROOT/rel).is_file():
        fail(f"required migration lineage missing: {rel}")

freeze=text("scripts/verify-production-freeze.sh")
for rel in registered:
    if Path(rel).name not in freeze and rel not in freeze:
        fail(f"production freeze lost required static gate: {rel}")
if "verify-release-candidate.py" not in freeze:
    fail("production freeze does not verify release-candidate contract")
release_tasks=text("scripts/release-tasks.sh")
for needle in (
    "verify-sourcing-manpower-master.py",
    "verify-sourcing-workforce-finder.py",
    "verify-sourcing-data-exchange.py",
    "verify-sourcing-scale-hardening.py",
    "verify-sourcing-security-certification.py",
    "verify-sourcing-browser-e2e.py",
    "apps.sourcing.tests.test_manpower_master",
    "apps.sourcing.tests.test_workforce_finder",
    "apps.sourcing.tests.test_data_exchange",
    "apps.sourcing.tests.test_scale_hardening",
    "apps.sourcing.tests.test_security_certification",
    "apps.sourcing.tests.test_browser_e2e_freeze",
    "verify-sourcing-vendor-verification.py",
    "verify-payroll-production-e2e.py",
):
    if needle not in release_tasks:
        fail(f"release tasks lost required verification: {needle}")

benchmarks=set(contract.get("required_benchmark_gates") or [])
if not any("certify-sourcing-browser-e2e.py" in gate for gate in benchmarks):
    fail("1.0.114 carry-forward release candidate must retain live Sourcing Chromium E2E")
if contract.get("sourcing_live_browser_evidence") != "sourcing-browser-certification.json":
    fail("1.0.114 carry-forward release candidate must retain the Sourcing browser evidence filename")

deploy=text(contract["deployment_entrypoint"])
if "scripts/verify-production-freeze.sh" not in deploy:
    fail("canonical production deployment no longer verifies the packaged freeze")

print("Verified SESCCO MS 1.0.114 Accounts Rental Supervisor Migration Hotfix release contract.")
