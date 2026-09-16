#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
PREDECESSOR = "1.0.115-inventory-manager-permission-reconciliation-hotfix"
PREDECESSOR_SHA = "023a01ec01f2c9d9101dbfa56a9dc8e60f0b46748e3d10542f8477ad9d260438"
CONTRACT = "merge/sourcing-https-test-transport-hotfix.json"
TESTS = (
    "apps/sourcing/tests/test_access_control.py",
    "apps/sourcing/tests/test_vendor_master.py",
    "apps/sourcing/tests/test_material_catalog.py",
    "apps/sourcing/tests/test_material_finder.py",
    "apps/sourcing/tests/test_vendor_verification.py",
    "apps/sourcing/tests/test_manpower_master.py",
    "apps/sourcing/tests/test_trade_workforce_catalog.py",
    "apps/sourcing/tests/test_workforce_finder.py",
    "apps/sourcing/tests/test_data_exchange.py",
    "apps/sourcing/tests/test_security_certification.py",
)


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING HTTPS TEST TRANSPORT HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read(CONTRACT))
if contract.get("release") != VERSION or contract.get("scope") != "sourcing-https-test-transport-hotfix":
    fail("contract identity mismatch")
if contract.get("previous_release") != PREDECESSOR or contract.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("predecessor identity/checksum mismatch")
if contract.get("test_only_setting_override") != "SECURE_SSL_REDIRECT=False":
    fail("test transport override changed")
for key in (
    "database_schema_change", "database_data_change", "permission_catalog_change",
    "permission_behavior_change", "payroll_formula_change", "inventory_quantity_change",
    "sourcing_business_rule_change",
):
    if contract.get(key) is not False:
        fail(f"{key} must remain false")
if contract.get("production_secure_ssl_redirect_default_preserved") is not True:
    fail("production HTTPS redirect must remain enabled by default")

production = read("config/settings/production.py")
if 'SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)' not in production:
    fail("production SECURE_SSL_REDIRECT default changed")

for rel in TESTS:
    text = read(rel)
    ast.parse(text, filename=rel)
    if "override_settings" not in text or "SECURE_SSL_REDIRECT=False" not in text:
        fail(f"Sourcing HTTP test is not protected from production redirect transport: {rel}")

access = read("apps/sourcing/tests/test_access_control.py")
for marker in (
    'self.assertEqual(response.status_code, 200)',
    'self.assertEqual(response.status_code, 403)',
    'self.assertFalse(membership_can_module(membership, PlatformModule.SOURCING))',
):
    if marker not in access:
        fail(f"access-control assertion lost: {marker}")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION:
    fail("release candidate version mismatch")
if "scripts/verify-sourcing-https-test-transport-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not retain HTTPS test transport verifier")
if "python manage.py test apps.sourcing.tests.test_access_control --noinput" not in set(release.get("required_runtime_gates") or []):
    fail("focused Sourcing access runtime test is no longer mandatory")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-sourcing-https-test-transport-hotfix.py" not in read(rel):
        fail(f"{rel} does not execute the hotfix verifier")

if "# 1.0.116 — Sourcing HTTPS Test Transport Hotfix\n" not in read("RELEASE_NOTES.md"):
    fail("historical 1.0.116 HTTPS test transport release notes were lost")

print("Verified SESCCO MS 1.0.117 Sourcing HTTPS test transport hotfix: production HTTPS unchanged, Sourcing HTTP tests reach application authorization, and no business/data authority changed.")
