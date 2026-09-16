#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.115"


def fail(message: str) -> None:
    raise SystemExit(f"USER MANAGEMENT UI ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/user-management-ui.json"))
if contract.get("release") != VERSION:
    fail("UI contract release does not match VERSION")
if contract.get("schema_change") is not False or contract.get("payroll_formula_change") is not False:
    fail("carried-forward Administration UI contract must remain schema-neutral and must not change Payroll formulas")
if contract.get("module", {}).get("path") != "/app/administration/":
    fail("Administration path changed")
if set(contract.get("register", {}).get("page_sizes") or []) != {25, 50, 100}:
    fail("User register page sizes changed")
if contract.get("register", {}).get("search_min_chars") != 2:
    fail("User search minimum changed")
if contract.get("register", {}).get("stale_request_cancellation") is not True:
    fail("User register must cancel stale requests")
if set(contract.get("scope_types") or []) != {"projects", "branches", "inventory_locations"}:
    fail("scope types changed")

modules = text("apps/accounts/modules.py")
for marker in (
    'ADMINISTRATION = "administration"',
    'normalized.startswith("/app/administration/")',
    'AccessPermission.ACCESS_USERS_VIEW',
    'return "accounts:administration"',
):
    if marker not in modules:
        fail(f"Administration module marker missing: {marker}")
context = text("apps/accounts/context.py")
for marker in ('"label": "Administration"', '"code": "AD"', 'reverse("accounts:administration")'):
    if marker not in context:
        fail(f"platform context marker missing: {marker}")
urls = text("apps/accounts/urls.py")
if 'path("app/administration/", administration_view, name="administration")' not in urls:
    fail("Administration route missing")
views = text("apps/accounts/views.py")
for marker in (
    '@access_permission_required(AccessPermission.ACCESS_USERS_VIEW)',
    '"accounts/administration.html"',
):
    if marker not in views:
        fail(f"Administration view guard missing: {marker}")

html = text("templates/accounts/administration.html")
for marker in (
    'id="accessUserSearch"', 'id="accessUserRows"', 'data-access-add-user',
    'id="accessDrawer"', 'administration-access-context',
    'platform/css/access-management.css', 'platform/js/access-management.js',
    'Django administration is separate',
):
    if marker not in html:
        fail(f"Administration template marker missing: {marker}")
if "get_role_display" in html:
    fail("Administration account label must use the effective Access Profile name, not role classification")

js = text("static/platform/js/access-management.js")
for marker in (
    '/api/access/users/', '/api/access/profiles/', '/api/access/scopes/lookup/',
    'AbortController', '320', 'access.users.manage', 'role-owner',
    'temporaryPassword', 'projectMode', 'branchMode', 'inventoryLocationMode',
    'Delete unused account', 'Reset Password',
):
    if marker not in js:
        fail(f"User Management JS marker missing: {marker}")
if "localStorage" in js or "sessionStorage" in js:
    fail("User Management authority must not be cached in browser storage")
if ".slice(0, 1000)" in js or "page_size=1000" in js:
    fail("User Management UI contains an unbounded directory path")

css = text("static/platform/css/access-management.css")
for marker in (".access-drawer", ".access-table-wrap", ".access-scope-results", "@media (max-width: 720px)"):
    if marker not in css:
        fail(f"User Management responsive CSS marker missing: {marker}")

switcher = text("templates/partials/platform_switchers.html")
if "PLATFORM_CONTEXT.current_module == 'administration'" not in switcher or "AD" not in switcher:
    fail("module switcher is not Administration-aware")

tests = text("apps/accounts/tests/test_user_management_ui.py")
for marker in (
    "test_administration_module_is_profile_authorized",
    "test_owner_user_management_page_renders_production_shell_and_api_hooks",
    "test_storekeeper_cannot_open_administration_and_does_not_see_module",
    "test_module_switcher_marks_administration_current",
):
    if marker not in tests:
        fail(f"UI regression missing: {marker}")

print("Verified SESCCO MS 1.0.115 Administration/User Management UI: permission-gated module, bounded register, production drawers, Access Profile assignment, explicit scopes and backend-authoritative security actions.")
