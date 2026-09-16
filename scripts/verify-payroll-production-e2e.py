#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL PRODUCTION E2E ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(text("merge/payroll-production-e2e.json"))
if contract.get("release") != "1.0.113":
    fail("certification contract release must be 1.0.113")

runner_rel = contract.get("runtime_runner")
if runner_rel != "scripts/certify-payroll-production-e2e.sh":
    fail("runtime runner changed without an explicit certification upgrade")
runner = text(runner_rel)
if "manage.py check --deploy --fail-level ERROR" not in runner:
    fail("runtime certification no longer performs Django deployment checks")
if "manage.py makemigrations --check --dry-run" not in runner:
    fail("runtime certification no longer rejects schema drift")
if 'manage.py test "${TEST_LABELS[@]}" --noinput' not in runner:
    fail("runtime certification no longer executes the curated Django suite")

labels = contract.get("runtime_test_labels") or []
required_labels = {
    "apps.core.tests.test_payroll_frontend",
    "apps.core.tests.test_payroll_attendance_contract",
    "apps.core.tests.test_payroll_action_parity",
    "apps.core.tests.test_payroll_data_authority",
    "apps.core.tests.test_payroll_output_e2e",
    "apps.core.tests.test_payroll_production_e2e",
    "apps.core.tests.test_payroll_performance",
    "apps.core.tests.test_payroll_query_hardening",
    "apps.core.tests.test_payroll_browser_scale",
    "apps.core.tests.test_payroll_seed_contract",
    "apps.core.tests.test_payroll_seed_profiles",
    "apps.internal_payroll.tests",
    "apps.rental_manpower.tests",
    "apps.documents.tests.test_documents",
    "apps.documents.tests.test_merge_access",
    "apps.core.tests.test_management_reporting",
    "apps.core.tests.test_merge_management_access",
    "apps.accounts.tests.test_granular_access",
    "apps.accounts.tests.test_user_management",
    "apps.accounts.tests.test_user_management_ui",
    "apps.inventory.tests.test_storekeeper_scope.StorekeeperScopedAuthorityTests",
    "apps.accounts.tests.test_custom_access_profiles",
    "apps.accounts.tests.test_cross_module_access_leaks",
    "apps.accounts.tests.test_session_security",
}
if not required_labels.issubset(set(labels)):
    missing = sorted(required_labels - set(labels))
    fail(f"runtime suite lost required test labels: {', '.join(missing)}")

required_verifiers = {
    "scripts/verify_payroll_frontend_contract.py",
    "scripts/verify-payroll-directory-runtime.py",
    "scripts/verify-payroll-action-parity.py",
    "scripts/verify-payroll-data-authority.py",
    "scripts/verify-payroll-output-e2e.py",
    "scripts/verify-payroll-document-production.py",
    "scripts/verify-full-demo-seed.py",
    "scripts/verify-payroll-scale-seed.py",
    "scripts/verify-payroll-performance.py",
    "scripts/verify-payroll-query-hardening.py",
    "scripts/verify-payroll-browser-scale.py",
    "scripts/verify-payroll-employee-residual-scale.py",
    "scripts/verify-payroll-salary-setup-scale.py",
    "scripts/verify-payroll-run-scale.py",
    "scripts/verify-payroll-adjustment-scale.py",
    "scripts/verify-payroll-assignment-project-selector-scale.py",
    "scripts/verify-payroll-drawer-selector-scale.py",
    "scripts/verify-payroll-rental-adjustment-selector-scale.py",
    "scripts/verify-payroll-rental-adjustment-page-scale.py",
    "scripts/verify-payroll-payment-scale.py",
    "scripts/verify-payroll-shared-surfaces-scale.py",
    "scripts/verify-payroll-report-performance.py",
    "scripts/verify-tenant-reconciliation.py",
    "scripts/verify-lifecycle-authority.py",
    "scripts/verify-lifecycle-retention-contract.py",
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
}
registered_verifiers = set(contract.get("static_verifiers") or [])
if not required_verifiers.issubset(registered_verifiers):
    fail("certification contract lost one or more prerequisite release verifiers")
for rel in required_verifiers:
    if not (ROOT / rel).is_file():
        fail(f"registered verifier does not exist: {rel}")

scenarios = contract.get("scenarios") or []
required_scenarios = {
    "access-and-workspace-authorization",
    "attendance-contract-and-submission",
    "internal-payroll-review-approval-integrity",
    "internal-wps-payment-reconciliation",
    "internal-master-lifecycle-recovery",
    "rental-assignment-timesheet-workflow",
    "rental-settlement-payment-integrity",
    "rental-master-lifecycle-recovery",
    "reports-documents-and-output-authority",
    "tenant-and-cross-module-boundaries",
    "seed-scale-and-performance-regression",
    "browser-scale-runtime-regression",
    "internal-employee-residual-scale-regression",
    "salary-setup-scale-regression",
    "payroll-run-scale-regression",
    "payroll-adjustment-scale-regression",
    "rental-assignment-project-selector-scale-regression",
    "cross-workspace-drawer-selector-scale-regression",
    "rental-adjustment-selector-scale-regression",
    "rental-adjustment-page-scale-regression",
    "payroll-document-production-hardening",
    "salary-payment-scale-regression",
    "shared-payroll-surfaces-scale-regression",
    "report-wps-performance-regression",
    "granular-access-authority-foundation",
    "single-access-authority-cutover",
    "user-management-backend-crud",
    "administration-user-management-ui",
    "rental-supervisor-foreman-scoped-access",
    "inventory-storekeeper-scoped-authority",
    "page-level-view-only-custom-profiles",
    "internal-payroll-finance-permission-decomposition",
    "cross-module-access-leak-closure",
    "credential-session-revocation-hardening",
}
scenario_ids = {row.get("id") for row in scenarios}
if not required_scenarios.issubset(scenario_ids):
    fail(f"certification scenarios incomplete: {sorted(required_scenarios - scenario_ids)}")

method_total = 0
files_checked: set[str] = set()
for scenario in scenarios:
    evidence = scenario.get("evidence") or {}
    if not evidence:
        fail(f"scenario {scenario.get('id')} has no Django regression evidence")
    for rel, required_methods in evidence.items():
        source = text(rel)
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            fail(f"{rel} is not valid Python: {exc}")
        discovered = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        }
        for method in required_methods:
            if method not in discovered:
                fail(f"scenario {scenario.get('id')} lost test evidence {rel}::{method}")
            method_total += 1
        files_checked.add(rel)

if method_total < 60:
    fail(f"certification evidence unexpectedly small: only {method_total} critical tests")
if len(files_checked) < 12:
    fail(f"certification evidence unexpectedly narrow: only {len(files_checked)} test files")

freeze = text("scripts/verify-production-freeze.sh")
if "verify-payroll-production-e2e.py" not in freeze:
    fail("production freeze does not enforce the Payroll production-E2E contract")
rehearsal = text("scripts/rehearse-production-freeze.sh")
for needle in (
    "certify-payroll-production-e2e.sh",
    "payroll-e2e-certification.txt",
    "run_manage test --noinput",
):
    if needle not in rehearsal:
        fail(f"production rehearsal lost Payroll certification evidence: {needle}")

release_tasks = text("scripts/release-tasks.sh")
if "verify-payroll-production-e2e.py" not in release_tasks:
    fail("release tasks do not enforce the static production-E2E contract")

print(
    f"Verified Payroll production-E2E certification: {len(scenarios)} scenarios, "
    f"{method_total} critical Django tests across {len(files_checked)} evidence files, "
    f"{len(labels)} runtime labels."
)
