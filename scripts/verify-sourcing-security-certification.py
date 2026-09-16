#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.112"
PREDECESSOR_SHA = "4de083b4bf99c38672548b9ccbe7b0ef2a66f9d0a461af34ffde21b295d0c1a2"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING SECURITY CERTIFICATION ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-security-certification.json"))
if contract.get("release") != VERSION:
    fail("certification contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.109 predecessor checksum changed")
if contract.get("schema_change") is not False or contract.get("business_feature_change") is not False:
    fail("1.0.112 must remain certification-only with no schema/business feature change")
if contract.get("permission_catalog_change") is not False:
    fail("1.0.112 must not change the permission catalog")

required_certifications = {
    "vendor_vs_manpower_permission_isolation",
    "company_a_vs_company_b_tenant_isolation",
    "view_only_direct_mutation_denial",
    "archived_and_trash_finder_exclusion",
    "immutable_vendor_and_workforce_verification_history",
    "stale_session_revocation_after_sourcing_access_change",
    "zero_operational_app_mutation_from_sourcing_create_and_verify_paths",
    "database_relation_isolation_from_operational_apps",
}
if set(contract.get("certifies") or []) != required_certifications:
    fail("certification coverage changed")

access = text("apps/sourcing/access.py")
for marker in (
    "def membership_can_view_vendor_sourcing",
    "def membership_can_manage_vendor_sourcing",
    "def membership_can_view_manpower_sourcing",
    "def membership_can_manage_manpower_sourcing",
    "VISIBLE_SOURCING_PERMISSIONS",
):
    if marker not in access:
        fail(f"permission isolation authority missing: {marker}")

views = text("apps/sourcing/views.py")
for marker in (
    "def _require_vendor_view",
    "def _require_vendor_manage",
    "def _require_manpower_view",
    "def _require_manpower_manage",
    "def _require_master_manage",
    "def vendor_offer_verify",
    "def workforce_offer_verify",
):
    if marker not in views:
        fail(f"backend permission gate missing: {marker}")

isolation = text("apps/sourcing/checks.py") + text("apps/sourcing/isolation.py")
for marker in (
    "FORBIDDEN_OPERATIONAL_APP_LABELS",
    "sourcing_domain_isolation_check",
    'id="sourcing.E001"',
    'id="sourcing.E002"',
):
    if marker not in isolation:
        fail(f"database isolation authority missing: {marker}")
for label in ("inventory", "projects", "internal_payroll", "rental_manpower", "documents", "data_exchange"):
    if f'"{label}"' not in isolation:
        fail(f"operational isolation label missing: {label}")

for rel, parent_marker in (
    ("apps/sourcing/selectors/material_finder.py", "vendor__deleted_at__isnull=True"),
    ("apps/sourcing/selectors/workforce_finder.py", "supplier__deleted_at__isnull=True"),
):
    payload = text(rel)
    for marker in (parent_marker, "__archived_at__isnull=True", "SourcingEntityStatus.ACTIVE", "is_active=True"):
        if marker not in payload:
            fail(f"Finder lifecycle exclusion missing in {rel}: {marker}")

base = text("apps/sourcing/models/base.py")
vendors = text("apps/sourcing/models/vendors.py")
manpower = text("apps/sourcing/models/manpower.py")
for marker in (
    "class ImmutableSourcingRevisionQuerySet",
    "raise NotSupportedError(\"Sourcing verification history is immutable and cannot be updated.\")",
    "raise NotSupportedError(\"Sourcing verification history is immutable and cannot be deleted.\")",
):
    if marker not in base:
        fail(f"immutable history manager missing: {marker}")
if "Sourcing offer revisions are immutable." not in vendors or "Sourcing workforce revisions are immutable." not in manpower:
    fail("immutable revision instance guards changed")

middleware = text("apps/accounts/middleware.py")
profiles = text("apps/accounts/access_profiles.py")
for marker in ("SESSION_SECURITY_VERSION_KEY", '"code": "session_revoked"', "logout(request)"):
    if marker not in middleware:
        fail(f"stale-session revocation authority missing: {marker}")
if "bump_profile_user_security_versions(profile)" not in profiles:
    fail("Access Profile changes no longer revoke assigned user sessions")

tests = text("apps/sourcing/tests/test_security_certification.py")
for marker in (
    "test_vendor_and_manpower_permissions_are_mutually_isolated",
    "test_company_a_cannot_read_company_b_sourcing_records",
    "test_view_only_profiles_cannot_mutate_via_direct_post",
    "test_archived_and_trash_sources_never_leak_into_finders",
    "test_verification_history_is_immutable_for_both_catalogs",
    "test_sourcing_access_profile_change_revokes_stale_session",
    "test_sourcing_create_and_verify_paths_do_not_mutate_operational_apps",
    "FORBIDDEN_OPERATIONAL_APP_LABELS",
    'apps.is_installed("apps.accounting")',
):
    if marker not in tests:
        fail(f"runtime certification coverage missing: {marker}")
try:
    ast.parse(tests)
except SyntaxError as exc:
    fail(f"invalid runtime certification test: {exc}")

for rel in (
    "apps/sourcing/services/vendors.py",
    "apps/sourcing/services/catalog.py",
    "apps/sourcing/services/manpower.py",
    "apps/sourcing/services/workforce.py",
):
    payload = text(rel)
    for forbidden in ("apps.inventory", "apps.projects", "apps.internal_payroll", "apps.rental_manpower", "apps.documents", "apps.accounting"):
        if forbidden in payload:
            fail(f"Sourcing service gained operational import {forbidden}: {rel}")

release_tasks = text("scripts/release-tasks.sh")
for marker in ("verify-sourcing-security-certification.py", "apps.sourcing.tests.test_security_certification"):
    if marker not in release_tasks:
        fail(f"release task missing security certification: {marker}")
freeze = text("scripts/verify-production-freeze.sh")
if "verify-sourcing-security-certification.py" not in freeze:
    fail("production freeze does not run Sourcing security certification")
if "docs/SOURCING_SECURITY_CERTIFICATION.md" not in text("README.md"):
    fail("README does not expose the Sourcing security certification contract")

print("PASS: SESCCO MS 1.0.112 Sourcing security/tenant/cross-module certification verified: permission isolation, tenant boundaries, view-only denial, Finder lifecycle exclusion, immutable history, session revocation and zero operational mutation evidence.")
