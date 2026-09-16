#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
PREDECESSOR_SHA = "a202be1a77f796734822d4356abc3a681c7850cc3e3a74ac4f9aab1cfc94e2cb"

def fail(message: str) -> None:
    raise SystemExit(f"PAGE-LEVEL VIEW-ONLY ERROR: {message}")

def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file(): fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

contract = json.loads(text("merge/page-level-view-only.json"))
if contract.get("release") != VERSION: fail("contract release must be 1.0.115")
if contract.get("schema_change") is not False: fail("1.0.115 must not introduce a schema migration")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA: fail("predecessor checksum changed")

profiles = text("apps/accounts/access_profiles.py")
for marker in (
    "create_access_profile", "update_access_profile", "delete_unused_access_profile",
    "Built-in Access Profiles are immutable", "You cannot modify the Access Profile currently granting your own authority",
    "_ACTION_VIEW_DEPENDENCIES", "requires its page permission", "access.profile.created", "access.profile.updated", "access.profile.deleted",
):
    if marker not in profiles: fail(f"custom profile authority marker missing: {marker}")

api = text("apps/accounts/access_api.py")
urls = text("apps/accounts/urls.py")
for marker in ("permissionCatalog", "serialize_access_profile", "create_access_profile", "update_access_profile", "delete_unused_access_profile"):
    if marker not in api: fail(f"custom profile API marker missing: {marker}")
if 'api/access/profiles/<uuid:profile_id>/' not in urls: fail("profile detail route missing")

perm = text("apps/accounts/api_permissions.py")
if "def api_method_access_required" not in perm or "page or action" not in perm: fail("exact method/page API guard missing")

for rel, markers in {
    "apps/internal_payroll/api.py": ("INTERNAL_EMPLOYEES_VIEW", "INTERNAL_EMPLOYEES_MANAGE", "INTERNAL_ORGANIZATION_VIEW", "INTERNAL_ORGANIZATION_MANAGE"),
    "apps/internal_payroll/attendance_api.py": ("INTERNAL_ATTENDANCE_VIEW", "INTERNAL_ATTENDANCE_EDIT", "INTERNAL_ATTENDANCE_SUBMIT", "INTERNAL_ATTENDANCE_APPROVE"),
    "apps/internal_payroll/payroll_api.py": ("INTERNAL_PAYROLL_RUNS_VIEW", "INTERNAL_PAYROLL_RUNS_PREPARE", "INTERNAL_ADJUSTMENTS_VIEW"),
    "apps/internal_payroll/salary_api.py": ("INTERNAL_SALARY_SETUP_VIEW", "INTERNAL_SALARY_SETUP_MANAGE"),
    "apps/internal_payroll/payment_api.py": ("INTERNAL_PAYMENTS_VIEW", "INTERNAL_PAYMENTS_PREPARE", "INTERNAL_WPS_VIEW", "INTERNAL_WPS_EXPORT"),
}.items():
    body = text(rel)
    if "api_method_access_required" not in body: fail(f"exact API guard not used by {rel}")
    for marker in markers:
        if marker not in body: fail(f"{rel} missing exact permission {marker}")

bootstrap = text("apps/core/payroll_views.py")
for marker in ("can_internal_master", "can_internal_attendance", "membership_has_permission", "INTERNAL_ATTENDANCE_VIEW"):
    if marker not in bootstrap: fail(f"exact bootstrap marker missing: {marker}")

frontend = text("static/payroll/js/app.js")
for marker in ("internalRoutePermissions", "firstAllowedWorkspaceRoute", "workspaceAllowsRoute", "internal.employees.view", "internal.attendance.view"):
    if marker not in frontend: fail(f"exact page-navigation marker missing: {marker}")

admin = text("static/platform/js/access-management.js")
template = text("templates/accounts/administration.html")
for marker in ("renderProfiles", "renderProfileForm", "applyViewOnlyMode", "permissionCatalog", "data-access-add-profile"):
    if marker not in admin and marker not in template: fail(f"Access Profile UI marker missing: {marker}")
if 'id="profiles"' not in template or 'id="accessProfileRows"' not in template: fail("Access Profiles page panel missing")

checks = text("apps/accounts/tests/test_custom_access_profiles.py")
for marker in (
    "test_profile_api_creates_custom_view_only_profile",
    "test_page_level_viewer_can_read_only_selected_internal_pages",
    "test_view_only_profile_cannot_mutate_a_page_it_can_read",
    "test_employee_only_viewer_bootstrap_does_not_receive_attendance_roster",
):
    if marker not in checks: fail(f"custom-profile regression missing: {marker}")

if "1.0.115" not in text("docs/PAGE_LEVEL_VIEW_ONLY.md"): fail("operator/security documentation missing")
print("PASS: SESCCO MS 1.0.115 page-level View Only and custom Access Profile contract verified.")
