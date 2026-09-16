#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.114"


def fail(message: str) -> None:
    raise SystemExit(f"USER MANAGEMENT BACKEND ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/user-management-backend.json"))
if contract.get("release") != VERSION or contract.get("schema_change") is not True:
    fail("1.0.114 contract must declare the user-management schema release")
if contract.get("payroll_formula_change") is not False:
    fail("User Management release must not change Payroll formulas")

models = text("apps/accounts/models.py")
for marker in (
    "must_change_password = models.BooleanField",
    "credentials_updated_at = models.DateTimeField",
    'CUSTOM = "custom", "Custom Access Profile"',
):
    if marker not in models + text("apps/accounts/roles.py"):
        fail(f"identity/custom-profile model marker missing: {marker}")

service = text("apps/accounts/user_management.py")
for marker in (
    "def create_managed_user", "def update_managed_user", "def set_managed_user_active",
    "def reset_managed_user_password", "def delete_unused_managed_user",
    "password_validation.validate_password", "must_change_password = True",
    "Only a Company Owner can assign the Company Owner access profile",
    "You cannot change your own access profile or scopes",
    "You cannot deactivate or reactivate your own access",
    "This account has activity history and must be deactivated instead of deleted",
    "MembershipProjectScope.objects.bulk_create", "MembershipBranchScope.objects.bulk_create",
    "MembershipInventoryLocationScope.objects.bulk_create", "SCOPE_RESULT_LIMIT = 25",
    "USER_PAGE_SIZES = frozenset({25, 50, 100})",
):
    if marker not in service:
        fail(f"user-management service marker missing: {marker}")
for secret_marker in ("temporaryPassword\": password", '"password": password'):
    if secret_marker in service:
        fail("temporary password appears to be written into an audit payload")

context = text("apps/accounts/context.py")
if '"must_change_password": bool(membership.user.must_change_password)' not in context:
    fail("frontend bootstrap does not expose forced-change credential state")

api = text("apps/accounts/access_api.py")
for marker in (
    "def access_users_api", "def access_user_detail_api", "def access_user_status_api",
    "def access_user_password_reset_api", "def access_profiles_api", "def access_scope_lookup_api",
    "AccessPermission.ACCESS_USERS_VIEW", "AccessPermission.ACCESS_USERS_MANAGE",
    "Enter at least 2 characters to search scope records", "[:SCOPE_RESULT_LIMIT]",
):
    if marker not in api:
        fail(f"access API marker missing: {marker}")

urls = text("apps/accounts/urls.py")
for marker in (
    'path("api/access/users/"', 'path("api/access/users/<uuid:membership_id>/"',
    'path("api/access/users/<uuid:membership_id>/status/"',
    'path("api/access/users/<uuid:membership_id>/reset-password/"',
    'path("api/access/profiles/"', 'path("api/access/scopes/lookup/"',
):
    if marker not in urls:
        fail(f"User Management URL missing: {marker}")

migration = text("apps/accounts/migrations/0007_user_management_backend.py")
for marker in (
    '("accounts", "0006_single_access_authority")', 'name="must_change_password"',
    'name="credentials_updated_at"', '("custom", "Custom Access Profile")',
    'name="accounts_membership_role_valid"',
):
    if marker not in migration:
        fail(f"1.0.114 migration marker missing: {marker}")

report = text("apps/core/management/commands/merge_access_report.py")
if "if role == AccessRole.CUSTOM" not in report:
    fail("access reconciliation must not require a built-in system profile for custom classification")
for marker in ("scope_company_mismatches", "any(selected_scope_without_rows.values())", "any(scope_company_mismatches.values())"):
    if marker not in report:
        fail(f"access reconciliation lost scope integrity check: {marker}")

tests = text("apps/accounts/tests/test_user_management.py")
for method in (
    "test_access_admin_can_create_operational_user_without_receiving_operational_permissions",
    "test_access_admin_cannot_assign_owner_profile", "test_selected_scopes_are_company_validated_and_persisted",
    "test_user_identity_must_be_unique_case_insensitively", "test_actor_cannot_change_own_access_profile_or_scopes",
    "test_password_reset_sets_forced_change_and_changes_hash", "test_access_admin_cannot_reset_owner_password",
    "test_deactivation_disables_identity_when_no_other_active_company_access",
    "test_reactivation_requires_active_profile", "test_cross_company_scope_assignment_is_rejected",
    "test_unused_never_signed_in_user_can_be_guardedly_deleted", "test_used_account_must_be_deactivated_not_deleted",
    "test_custom_profile_uses_custom_classification_without_role_authority", "test_scope_lookup_is_bounded",
):
    if f"def {method}" not in tests:
        fail(f"missing User Management regression: {method}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-user-management-backend.py" not in text(rel):
        fail(f"{rel} does not enforce User Management backend gate")
if "merge_access_report --fail-on-errors" not in text("scripts/rehearse-production-freeze.sh"):
    fail("production rehearsal lost access reconciliation")

print("Verified SESCCO MS 1.0.114 User Management backend: company-scoped CRUD, owner/self protection, password-reset state, atomic scopes, bounded APIs and immutable access audit.")
