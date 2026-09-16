#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"
PREDECESSOR_SHA = "801d25b6f65a898f7f0dc96044df1e868949ff84db8547aff1ccc42788453ca4"


def fail(message: str) -> None:
    raise SystemExit(f"ACCESS HISTORY ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/access-history-recovery.json"))
if contract.get("release") != VERSION:
    fail("contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("predecessor checksum changed")
if contract.get("schema_change") is not False:
    fail("1.0.115 must remain schema-neutral")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Access History must not change Payroll or Inventory formulas")

history = text("apps/accounts/access_history.py")
for marker in (
    "def access_history_page(",
    "def user_access_history(",
    "AccessPermission.ACCESS_AUDIT_VIEW",
    "AuditArea.ACCESS",
    "ACCESS_AUDIT_PAGE_SIZES = frozenset({25, 50, 100})",
    "offset + size + 1",
    '"restorableBefore"',
):
    if marker not in history:
        fail(f"Access History authority missing: {marker}")

users = text("apps/accounts/user_management.py")
for marker in (
    "def restore_managed_user_access(",
    "AccessPermission.ACCESS_AUDIT_VIEW",
    "You cannot restore your own historical access configuration.",
    "_profile_for_assignment(",
    "parse_scope_assignment(",
    "_apply_scope_assignment(",
    "bump_user_security_version(target.user_id)",
    'action="access.user.access_restored"',
    '"sourceEventId": str(source_event.pk)',
    '"snapshotSide": "before"',
):
    if marker not in users:
        fail(f"guarded recovery authority missing: {marker}")

api = text("apps/accounts/access_api.py")
for marker in (
    "def access_audit_api(",
    "def access_user_history_api(",
    "def access_user_restore_api(",
    "AccessPermission.ACCESS_USERS_MANAGE",
    "AccessPermission.ACCESS_AUDIT_VIEW",
):
    if marker not in api:
        fail(f"Access History API boundary missing: {marker}")
urls = text("apps/accounts/urls.py")
for marker in (
    'name="access-audit-api"',
    'name="access-user-history-api"',
    'name="access-user-restore-api"',
):
    if marker not in urls:
        fail(f"Access History URL missing: {marker}")

template = text("templates/accounts/administration.html")
for marker in ("Access History", 'id="history"', 'id="accessHistoryRows"', "?v=1.0.115"):
    if marker not in template:
        fail(f"Administration Access History UI missing: {marker}")
js = text("static/platform/js/access-management.js")
for marker in (
    'const canViewAudit = permissionSet.has("access.audit.view")',
    "async function loadAccessHistory(",
    "async function renderUserHistory(",
    "function renderAccessRestore(",
    "/restore-access/",
    "Restore Prior Access",
):
    if marker not in js:
        fail(f"Access History browser client missing: {marker}")

source = text("apps/accounts/tests/test_access_history.py")
try:
    tree = ast.parse(source)
except SyntaxError as exc:
    fail(f"Access History regression file invalid: {exc}")
methods = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")}
required = {
    "test_access_history_is_company_scoped_and_permission_guarded",
    "test_user_history_marks_only_recoverable_before_snapshots",
    "test_restore_reapplies_prior_profile_and_scope_and_revokes_sessions",
    "test_restore_requires_exact_username_confirmation",
    "test_access_history_api_and_user_history_api",
}
if not required.issubset(methods):
    fail(f"runtime regressions missing: {sorted(required - methods)}")
if "1.0.115" not in text("docs/ACCESS_HISTORY_RECOVERY.md"):
    fail("operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.115 immutable Access History and guarded prior-access recovery are release-bound.")
