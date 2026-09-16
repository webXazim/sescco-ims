#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.113"
PREDECESSOR_SHA = "a94d4a289abac628d6305db7def2c41e4255ae6def8bab1dad89f13f667b4751"


def fail(message: str) -> None:
    raise SystemExit(f"SESSION SECURITY ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/credential-session-revocation-hardening.json"))
if contract.get("release") != VERSION:
    fail("contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("security_version migration must be declared")
if contract.get("payroll_formula_change") is not False:
    fail("session hardening must not change Payroll formulas")

model = text("apps/accounts/models.py")
if "security_version = models.PositiveBigIntegerField(default=1)" not in model:
    fail("User.security_version is missing")
migration = text("apps/accounts/migrations/0011_user_security_version.py")
for marker in ('name="security_version"', 'PositiveBigIntegerField(default=1)'):
    if marker not in migration:
        fail(f"migration marker missing: {marker}")

security = text("apps/accounts/security.py")
for marker in ("SESSION_SECURITY_VERSION_KEY", "def bump_user_security_version(", "def bump_profile_user_security_versions(", "def stamp_security_session("):
    if marker not in security:
        fail(f"security helper missing: {marker}")

middleware = text("apps/accounts/middleware.py")
for marker in ("class SecuritySessionMiddleware", 'code": "session_revoked"', "class MandatoryPasswordChangeMiddleware", 'code": "password_change_required"'):
    if marker not in middleware:
        fail(f"middleware authority missing: {marker}")
settings = text("config/settings/base.py")
order = [
    '"django.contrib.auth.middleware.AuthenticationMiddleware"',
    '"apps.accounts.middleware.SecuritySessionMiddleware"',
    '"apps.accounts.middleware.CompanyContextMiddleware"',
    '"apps.accounts.middleware.MandatoryPasswordChangeMiddleware"',
]
pos = [settings.find(marker) for marker in order]
if any(value < 0 for value in pos) or pos != sorted(pos):
    fail("security middleware order is not authentication -> session stamp -> company -> mandatory password")

users = text("apps/accounts/user_management.py")
if users.count("bump_user_security_version(") < 3:
    fail("managed user profile/scope/status/password changes are not session-revoking")
profiles = text("apps/accounts/access_profiles.py")
if "bump_profile_user_security_versions(profile)" not in profiles:
    fail("Access Profile edits do not revoke assigned sessions")
services = text("apps/accounts/services.py")
if services.count("bump_user_security_version(") < 2:
    fail("legacy membership role/status services are not session-revoking")

views = text("apps/accounts/views.py")
for marker in ("def change_password_view(", "update_session_auth_hash", 'action="access.user.password_changed"', "SESSION_SECURITY_VERSION_KEY"):
    if marker not in views:
        fail(f"password-change flow missing: {marker}")
urls = text("apps/accounts/urls.py")
if 'name="change-password"' not in urls:
    fail("password-change URL missing")
if "Change temporary password" not in text("templates/registration/change_password.html"):
    fail("password-change UI missing")

source = text("apps/accounts/tests/test_session_security.py")
try:
    tree = ast.parse(source)
except SyntaxError as exc:
    fail(f"session security regression file invalid: {exc}")
methods = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")}
required = {
    "test_pre_upgrade_session_is_stamped_on_first_request",
    "test_access_profile_change_revokes_existing_session_on_next_request",
    "test_scope_change_revokes_api_session_with_explicit_401",
    "test_custom_profile_permission_edit_revokes_every_assigned_user_session",
    "test_deactivate_then_reactivate_before_next_request_still_revokes_old_session",
    "test_temporary_password_blocks_operations_until_changed",
}
if not required.issubset(methods):
    fail(f"runtime regressions missing: {sorted(required - methods)}")
if "1.0.113" not in text("docs/CREDENTIAL_SESSION_REVOCATION.md"):
    fail("operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.113 credential/session revocation and mandatory temporary-password change are release-bound.")
