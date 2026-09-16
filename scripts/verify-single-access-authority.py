#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.114"


def fail(message: str) -> None:
    raise SystemExit(f"SINGLE ACCESS AUTHORITY ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/single-access-authority.json"))
if contract.get("release") != VERSION:
    fail("single-access-authority contract release mismatch")
if contract.get("schema_change") is not True or contract.get("payroll_formula_change") is not False:
    fail("1.0.114 must declare the Accounts authorization schema change and no Payroll formula change")
authority = contract.get("authority") or {}
for key in (
    "user_role_removed", "access_profile_required", "missing_profile_fails_closed",
    "django_staff_reserved_for_superusers",
):
    if authority.get(key) is not True:
        fail(f"authority flag must be true: {key}")
if authority.get("membership_role_runtime_authority") is not False:
    fail("CompanyMembership.role must not remain a runtime authorization authority")

models = text("apps/accounts/models.py")
user_block = models.split("class User(AbstractUser):", 1)[-1].split("class ScopeMode", 1)[0]
if re.search(r"^\s+role\s*=\s*models\.", user_block, re.M) or "class Role(models.TextChoices)" in user_block:
    fail("accounts.User still defines legacy application role authority")
if "is_inventory_admin" in user_block:
    fail("accounts.User still exposes legacy Inventory admin authority")
for marker in (
    "desired_staff = bool(self.is_superuser)",
    "Authoritative SESCCO application access profile",
    "Compatibility classification only; AccessProfile is the authorization authority",
    "access_profile__key=owner_key",
    "ensure_system_access_profile(company=self.company, role=self.role)",
):
    if marker not in models:
        fail(f"model authority marker missing: {marker}")
access_field = models.split("access_profile = models.ForeignKey(", 1)[-1].split(")\n", 1)[0]
if "null=True" in access_field or "blank=True" in access_field:
    fail("CompanyMembership.access_profile must be required in 1.0.114")

policy = text("apps/accounts/access_policy.py")
if "permissions_for_legacy_role" in policy or "membership.role" in policy:
    fail("EffectiveAccess still evaluates legacy membership role")
for marker in (
    'profile_key = "missing-profile"',
    "values = frozenset()",
    "grant.permission for grant in profile.permission_grants.all()",
):
    if marker not in policy:
        fail(f"EffectiveAccess fail-closed/profile marker missing: {marker}")

permissions = text("apps/accounts/permissions.py")
if "role_definition(membership.role)" in permissions or "membership.role" in permissions:
    fail("workspace/capability compatibility helpers still evaluate membership role")
for marker in (
    "effective_access_for_membership", "INVENTORY_VIEW_PERMISSIONS", "INTERNAL_VIEW_PERMISSIONS",
    "RENTAL_VIEW_PERMISSIONS", "def membership_can_workspace", "def membership_can_edit",
    "def membership_has_capability", "AccessPermission.SETTINGS_MANAGE",
    "AccessPermission.ACCESS_AUDIT_VIEW", "AccessPermission.ACCESS_USERS_MANAGE",
):
    if marker not in permissions:
        fail(f"profile-derived compatibility authority missing: {marker}")

context = text("apps/accounts/context.py")
for marker in (
    "membership_can_workspace(membership, workspace)",
    "membership_can_edit(membership, workspace)",
    "membership_has_capability(membership, capability)",
    '"edit_workspaces": edit_workspaces',
):
    if marker not in context:
        fail(f"request access context is not profile-derived: {marker}")

js = text("static/payroll/js/app.js")
for forbidden in (
    "roleDefinition().edit.includes", "roleDefinition().approve", "roleDefinition().pay",
    "roleDefinition().settings", "roleDefinition().view_access",
):
    if forbidden in js:
        fail(f"Payroll browser still grants UI authority from role matrix: {forbidden}")
for marker in (
    "serverEditWorkspaces", "serverCapabilities", "roleCanViewAccess()",
    "accessProfileLabel()", "serverAccess.effective_access?.permissions",
):
    if marker not in js:
        fail(f"Payroll browser profile-derived authority missing: {marker}")

admin = text("apps/accounts/admin.py")
if '"role",' in admin.split("@admin.register(User)", 1)[-1].split("@admin.register(CompanyMembership)", 1)[0]:
    fail("Django User admin still exposes removed User.role")
if "Django staff access is reserved for superusers" not in admin:
    fail("Django admin/application admin separation guidance is missing")

services = text("apps/accounts/services.py")
if "access_profile__key=owner_key" not in services:
    fail("membership owner protection still depends on role instead of owner profile")
if "ensure_system_access_profile" not in services:
    fail("system profile provisioning service is missing")

migration = text("apps/accounts/migrations/0006_single_access_authority.py")
for marker in (
    '("accounts", "0005_granular_access_authority")',
    "def enforce_profile_authority", "is_superuser=False, is_staff=True",
    'name="access_profile"', 'name="role"', "migrations.RemoveField",
    "Missing system access profile", "Authoritative SESCCO application access profile",
):
    if marker not in migration:
        fail(f"1.0.114 migration marker missing: {marker}")

report = text("apps/core/management/commands/merge_access_report.py")
for marker in (
    "non_superuser_django_staff_accounts", "access_profile__key=owner_key",
    "memberships_without_access_profile", "membership_profile_company_mismatches",
):
    if marker not in report:
        fail(f"access reconciliation cutover check missing: {marker}")

seed = text("apps/core/management/commands/seed_payroll_test_data.py")
if "memberships__role=AccessRole.OWNER" in seed or ".filter(company=company, role=AccessRole.OWNER" in seed:
    fail("Payroll seed still treats membership role as owner authority")
if "system_profile_key_for_role(AccessRole.OWNER)" not in seed:
    fail("Payroll seed is not using owner profile authority")

tests = text("apps/accounts/tests/test_granular_access.py")
for method in (
    "test_system_profile_provisioning_preserves_existing_role_permissions",
    "test_role_classification_cannot_override_assigned_profile",
    "test_missing_profile_fails_closed_without_role_fallback",
):
    if f"def {method}" not in tests:
        fail(f"missing single-authority regression: {method}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-single-access-authority.py" not in text(rel):
        fail(f"{rel} does not enforce the single access authority gate")
if "merge_access_report --fail-on-errors" not in text("scripts/rehearse-production-freeze.sh"):
    fail("production rehearsal lost access reconciliation")

print("Verified SESCCO MS 1.0.114 single authorization authority: User.role retired, profile-only runtime decisions, owner/profile protection, Django-admin separation and fail-closed reconciliation.")
