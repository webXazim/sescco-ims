#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
EXPECTED_PERMISSION_COUNT = 94
EXPECTED_ROLES = {
    "owner", "operations-admin", "access-admin", "inventory-manager", "storekeeper",
    "finance", "internal-officer", "rental-officer", "rental-supervisor", "reviewer", "auditor",
}


def fail(message: str) -> None:
    raise SystemExit(f"GRANULAR ACCESS AUTHORITY ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/granular-access-authority.json"))
if contract.get("release") != VERSION:
    fail("access-authority contract release mismatch")
if contract.get("permission_catalog_size") != EXPECTED_PERMISSION_COUNT:
    fail("permission catalog size contract changed")
if set(contract.get("system_profiles") or []) != EXPECTED_ROLES:
    fail("built-in access profile set changed")
if (contract.get("authority") or {}).get("legacy_role_bridge") is not False:
    fail("1.0.117 must keep the legacy runtime role bridge retired")

catalog = text("apps/accounts/access_catalog.py")
class_block = catalog.split("class AccessPermission(StrEnum):", 1)[-1].split("_PERMISSION_LABELS", 1)[0]
permissions = re.findall(r'^\s+[A-Z0-9_]+\s*=\s*"([^"]+)"', class_block, flags=re.M)
if len(permissions) != EXPECTED_PERMISSION_COUNT or len(set(permissions)) != EXPECTED_PERMISSION_COUNT:
    fail(f"AccessPermission must contain exactly {EXPECTED_PERMISSION_COUNT} unique keys")
for required in (
    "access.users.manage", "access.profiles.manage", "inventory.stock.receive", "inventory.stock.transfer",
    "inventory.movements.reverse", "internal.attendance.edit", "internal.payroll_runs.approve",
    "internal.payments.execute", "internal.payroll_runs.review", "rental.timesheets.edit", "rental.timesheets.submit",
    "rental.settlements.approve", "rental.payments.execute",
    "sourcing.vendors.view", "sourcing.vendors.manage", "sourcing.manpower.view",
    "sourcing.manpower.manage", "sourcing.masters.view", "sourcing.masters.manage",
    "sourcing.export.execute",
):
    if required not in permissions:
        fail(f"permission catalog lost required authority: {required}")
# Role definitions remain only templates for built-in system profiles.
for marker in ("def permissions_for_legacy_role", "if role == AccessRole.OWNER", "return frozenset(AccessPermission)"):
    if marker not in catalog:
        fail(f"system-profile template mapping missing: {marker}")

models = text("apps/accounts/models.py")
for marker in (
    "class ScopeMode(models.TextChoices)", "class AccessProfile(UUIDTimeStampedModel)",
    "class AccessProfilePermission(UUIDTimeStampedModel)", "access_profile = models.ForeignKey(",
    "project_scope_mode = models.CharField", "branch_scope_mode = models.CharField",
    "inventory_location_scope_mode = models.CharField", "class MembershipProjectScope(UUIDTimeStampedModel)",
    "class MembershipBranchScope(UUIDTimeStampedModel)", "class MembershipInventoryLocationScope(UUIDTimeStampedModel)",
    'name="accounts_profile_permission_valid"', "Access profile must belong to the same company",
    "Project scope must belong to the membership company", "Branch scope must belong to the membership company",
    "Inventory location scope must belong to the membership company",
):
    if marker not in models:
        fail(f"access model authority missing: {marker}")

policy = text("apps/accounts/access_policy.py")
for marker in (
    "class EffectiveAccess", "def effective_access_for_membership", 'getattr(membership, "_effective_access_cache", None)',
    "def membership_has_permission", "def membership_allows_project", "def membership_allows_branch",
    "def membership_allows_inventory_location", "def restrict_projects", "def restrict_branches",
    "def restrict_inventory_locations", 'grant.permission for grant in profile.permission_grants.all()',
    'profile_key = "missing-profile"',
):
    if marker not in policy:
        fail(f"effective-access policy marker missing: {marker}")
if "permissions_for_legacy_role" in policy or "membership.role" in policy:
    fail("EffectiveAccess regressed to role-based permission fallback")

selectors = text("apps/accounts/selectors.py")
if '.select_related("company", "company__settings", "user", "access_profile")' not in selectors:
    fail("membership resolution does not fetch Access Profile")
if '.prefetch_related("access_profile__permission_grants")' not in selectors:
    fail("membership resolution does not prefetch granular permission grants")

middleware = text("apps/accounts/middleware.py")
for marker in ("request.effective_access = None", "effective_access_for_membership(membership)"):
    if marker not in middleware:
        fail(f"request effective-access snapshot missing: {marker}")
context = text("apps/accounts/context.py")
if '"effective_access": effective_access.as_frontend_dict() if effective_access else {}' not in context:
    fail("frontend context does not expose the bounded effective-access snapshot")
if '"edit_workspaces": edit_workspaces' not in context:
    fail("frontend context does not expose profile-derived edit authority")

migration = text("apps/accounts/migrations/0005_granular_access_authority.py")
if "def backfill_access_profiles" not in migration:
    fail("1.0.88 profile/scope foundation migration is missing")
cutover = text("apps/accounts/migrations/0006_single_access_authority.py")
rental_supervisor = text("apps/accounts/migrations/0008_rental_supervisor_profile.py")
for marker in ('("rental-supervisor", "Rental Supervisor / Foreman")', 'key="role-rental-supervisor"'):
    if marker not in rental_supervisor:
        fail(f"1.0.117 Rental Supervisor profile migration marker missing: {marker}")
for marker in ("def enforce_profile_authority", 'name="access_profile"', 'name="role"'):
    if marker not in cutover:
        fail(f"1.0.117 authority cutover migration marker missing: {marker}")

report = text("apps/core/management/commands/merge_access_report.py")
for marker in (
    "memberships_without_access_profile", "membership_profile_company_mismatches",
    "missing_system_access_profiles", "system_profile_permission_drift",
    "non_superuser_django_staff_accounts",
):
    if marker not in report:
        fail(f"production access reconciliation lost check: {marker}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-granular-access-authority.py" not in text(rel):
        fail(f"{rel} does not enforce granular access authority")
if "merge_access_report --fail-on-errors" not in text("scripts/rehearse-production-freeze.sh"):
    fail("production rehearsal lost company/access reconciliation")

print("Verified SESCCO MS 1.0.117 granular access authority: 94 permissions including independent Sourcing grants, system profiles, explicit scopes, request cache and profile-only runtime authority.")
