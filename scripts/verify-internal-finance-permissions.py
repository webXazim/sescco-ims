#!/usr/bin/env python3
from __future__ import annotations
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
PREDECESSOR_SHA = "9920b4009f29fdf1dd09db51bb5fdf5c29eb4ecc32c937961c5537e0fa20e6d3"

def fail(message: str) -> None:
    raise SystemExit(f"INTERNAL FINANCE PERMISSION ERROR: {message}")

def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file(): fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

if text("VERSION").strip() != VERSION: fail("VERSION must be 1.0.115")
contract = json.loads(text("merge/internal-finance-permission-decomposition.json"))
if contract.get("release") != VERSION: fail("contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA: fail("1.0.115 predecessor checksum changed")
if contract.get("schema_change") is not True: fail("1.0.115 must declare its permission/review-signoff schema change")
if contract.get("payroll_formula_change") is not False: fail("permission decomposition must not change Payroll formulas")
if contract.get("operator_guide") != "docs/INTERNAL_FINANCE_PERMISSIONS.md": fail("operator guide binding changed")
if "Finance Manager" not in text("docs/INTERNAL_FINANCE_PERMISSIONS.md") or "final approver cannot be the payroll submitter or the Finance Reviewer" not in text("docs/INTERNAL_FINANCE_PERMISSIONS.md"):
    fail("operator guide does not document enforced duty separation")

catalog = text("apps/accounts/access_catalog.py")
for marker in (
    'INTERNAL_PAYROLL_RUNS_REVIEW = "internal.payroll_runs.review"',
    'AccessRole.INTERNAL_PAYROLL_OFFICER', 'AccessRole.FINANCE_REVIEWER', 'AccessRole.FINANCE_MANAGER',
    'AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW', 'AccessPermission.INTERNAL_PAYMENTS_EXECUTE',
):
    if marker not in catalog: fail(f"permission catalog marker missing: {marker}")


if 'if role == AccessRole.FINANCE_MANAGER:' not in catalog:
    fail("Finance Manager system profile template missing")
finance_block = catalog.split('if role == AccessRole.FINANCE_MANAGER:', 1)[1].split('if role == AccessRole.STOREKEEPER:', 1)[0]
if 'AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW' in finance_block:
    fail("Finance Manager must not inherit Finance Review authority")

profiles = text("apps/accounts/access_profiles.py")
if 'AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW.value: AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW.value' not in profiles:
    fail("custom-profile review permission dependency missing")
if 'value.endswith(".review")' not in profiles:
    fail("Finance Review must be classified as an action permission for View-only profiles")

model = text("apps/internal_payroll/models/payroll.py")
for marker in ('reviewed_at = models.DateTimeField', 'reviewed_by = models.ForeignKey', 'reviewed_internal_payroll_runs'):
    if marker not in model: fail(f"PayrollRun finance-review evidence missing: {marker}")

service = text("apps/internal_payroll/services/payroll.py")
for marker in (
    'def _require_payroll_prepare', 'def _require_payroll_review', 'def _require_payroll_approval',
    'normalized in {"review", "return_for_changes"}', 'audit_action = "internal.payroll_run.reviewed"',
    'Finance Review sign-off is required before final approval', 'run.reviewed_at = now', 'run.reviewed_by = actor_membership.user',
    'Finance Review must be completed by a different user from the payroll submitter',
    'Final approval must be completed by a different user from the Finance Reviewer',
    'Final approval must be completed by a different user from the payroll submitter',
):
    if marker not in service: fail(f"Payroll workflow separation marker missing: {marker}")

attendance = text("apps/internal_payroll/services/attendance.py")
for marker in ('def _require_attendance_edit', 'def _require_attendance_submit', 'def _require_attendance_approval'):
    if marker not in attendance: fail(f"attendance duty separation missing: {marker}")

payment = text("apps/internal_payroll/services/payment.py")
for marker in ('def _require_payment_prepare', 'def _require_wps_export', 'def _require_payment_execute'):
    if marker not in payment: fail(f"payment duty separation missing: {marker}")
if 'export_salary_payment_batch' not in payment or '_require_wps_export(actor_membership)' not in payment:
    fail("Bank/WPS export must use WPS export authority")

for rel, markers in {
    "apps/internal_payroll/payroll_api.py": (
        'INTERNAL_PAYROLL_RUNS_REVIEW', '_require_action_permission(request, required_permission)',
        'INTERNAL_ADJUSTMENTS_APPROVE',
    ),
    "apps/internal_payroll/attendance_api.py": ('INTERNAL_ATTENDANCE_SUBMIT', 'INTERNAL_ATTENDANCE_APPROVE', '_require_action_permission'),
    "apps/internal_payroll/payment_api.py": ('INTERNAL_PAYMENTS_PREPARE', 'INTERNAL_PAYMENTS_EXECUTE', 'INTERNAL_WPS_EXPORT', '_require_action_permission'),
}.items():
    body = text(rel)
    for marker in markers:
        if marker not in body: fail(f"{rel} action-level authority missing: {marker}")

selector = text("apps/internal_payroll/selectors/payroll.py")
for marker in ('"canReview": "review" in allowed_actions', '"reviewSignedOff": review_signed_off', 'INTERNAL_PAYROLL_RUNS_REVIEW'):
    if marker not in selector: fail(f"server workflow projection missing: {marker}")
payment_selector = text("apps/internal_payroll/selectors/payment.py")
for marker in ('"canPrepare": can_prepare', '"canExport": can_export', 'INTERNAL_PAYMENTS_EXECUTE', 'INTERNAL_WPS_EXPORT'):
    if marker not in payment_selector: fail(f"payment projection separation missing: {marker}")

frontend = text("static/payroll/js/app.js")
for marker in (
    'data-review-mark', "requestPayrollWorkflow('review'", 'reviewSignedOff',
    "hasAccessPermission('internal.payroll_runs.review')", "hasAccessPermission('internal.payroll_runs.approve')",
    "hasAccessPermission('internal.payments.prepare')", "hasAccessPermission('internal.wps.export')", "hasAccessPermission('internal.payments.execute')",
):
    if marker not in frontend: fail(f"frontend exact-authority marker missing: {marker}")

for rel in contract.get("migrations") or []:
    source = text(rel)
    try: ast.parse(source)
    except SyntaxError as exc: fail(f"migration is invalid Python: {rel}: {exc}")

for rel, methods in {
    "apps/accounts/tests/test_finance_permissions.py": (
        'test_internal_payroll_officer_prepares_but_cannot_review_or_final_approve',
        'test_finance_reviewer_can_review_but_not_final_approve',
        'test_finance_manager_can_final_approve_and_execute_without_payroll_preparation',
    ),
    "apps/internal_payroll/tests/test_payroll.py": (
        'test_final_approval_requires_independent_review_signoff',
        'test_finance_reviewer_cannot_final_approve_after_signoff',
        'test_finance_review_must_be_by_different_user_from_submitter',
        'test_final_approver_must_differ_from_finance_reviewer',
        'test_final_approver_must_differ_from_payroll_submitter',
    ),
    "apps/internal_payroll/tests/test_payment.py": ('test_wps_export_permission_is_independent_from_payment_execution',),
}.items():
    body=text(rel)
    for method in methods:
        if f"def {method}(" not in body: fail(f"regression missing: {rel}::{method}")

print("PASS: SESCCO MS 1.0.115 Internal Payroll + Finance permission decomposition verified.")
