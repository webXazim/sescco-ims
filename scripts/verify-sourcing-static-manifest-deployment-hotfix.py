#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
PREDECESSOR = "1.0.116-sourcing-https-test-transport-hotfix"
PREDECESSOR_SHA = "b556f03f6d499862eeb9dd5f9527c3dc14a706a28c64cb8ea3e48b0688bdd94c"
CONTRACT = "merge/sourcing-static-manifest-deployment-hotfix.json"
HTTP_TESTS = (
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
ASSETS = (
    "sourcing/css/directory.css",
    "sourcing/js/finder-scale.js",
    "sourcing/js/manpower-directory.js",
    "sourcing/js/vendor-directory.js",
)


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING STATIC MANIFEST HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read(CONTRACT))
if contract.get("release") != VERSION or contract.get("scope") != "sourcing-static-manifest-deployment-hotfix":
    fail("contract identity mismatch")
if contract.get("previous_release") != PREDECESSOR or contract.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("predecessor identity/checksum mismatch")
if contract.get("test_static_backend") != "django.contrib.staticfiles.storage.StaticFilesStorage":
    fail("test static backend changed")
if contract.get("production_static_backend") != "django.contrib.staticfiles.storage.ManifestStaticFilesStorage":
    fail("production static backend changed")
for key in (
    "database_schema_change", "database_data_change", "permission_catalog_change",
    "permission_behavior_change", "payroll_formula_change", "inventory_quantity_change",
    "sourcing_business_rule_change", "production_https_policy_change",
):
    if contract.get(key) is not False:
        fail(f"{key} must remain false")

production = read("config/settings/production.py")
if '"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"' not in production:
    fail("production ManifestStaticFilesStorage authority changed")
if 'SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)' not in production:
    fail("production HTTPS redirect default changed")

support = read("apps/sourcing/tests/support.py")
ast.parse(support, filename="apps/sourcing/tests/support.py")
if '"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}' not in support:
    fail("Sourcing test static backend is not plain StaticFilesStorage")

for rel in HTTP_TESTS:
    text = read(rel)
    ast.parse(text, filename=rel)
    if "SECURE_SSL_REDIRECT=False" not in text:
        fail(f"HTTPS test transport override missing: {rel}")
    if "STORAGES=SOURCING_HTTP_TEST_STORAGES" not in text:
        fail(f"pre-collectstatic test manifest isolation missing: {rel}")

for asset in ASSETS:
    if not (ROOT / "static" / asset).is_file():
        fail(f"source static asset missing: static/{asset}")

command = read("apps/sourcing/management/commands/verify_sourcing_static_manifest.py")
ast.parse(command, filename="apps/sourcing/management/commands/verify_sourcing_static_manifest.py")
for asset in ASSETS:
    if asset not in command:
        fail(f"post-collectstatic manifest command does not verify {asset}")

release_tasks = read("scripts/release-tasks.sh")
test_pos = release_tasks.find("Running focused Sourcing domain/isolation regression")
collect_pos = release_tasks.find("run_manage collectstatic --noinput")
manifest_pos = release_tasks.find("run_manage verify_sourcing_static_manifest")
bootstrap_pos = release_tasks.find("run_manage payroll_bootstrap_report --fail-on-errors")
if min(test_pos, collect_pos, manifest_pos, bootstrap_pos) < 0:
    fail("release task markers missing")
if not (test_pos < collect_pos < manifest_pos < bootstrap_pos):
    fail("safe tests -> collectstatic -> manifest verification -> bootstrap order changed")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION or release.get("release_type") != "sourcing-static-manifest-deployment-hotfix":
    fail("release candidate identity mismatch")
if release.get("previous_release") != PREDECESSOR or release.get("previous_archive_sha256") != PREDECESSOR_SHA:
    fail("release candidate predecessor mismatch")
if "scripts/verify-sourcing-static-manifest-deployment-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not require static-manifest hotfix verifier")
for gate in ("python manage.py collectstatic --noinput", "python manage.py verify_sourcing_static_manifest"):
    if gate not in set(release.get("required_runtime_gates") or []):
        fail(f"release candidate runtime gate missing: {gate}")

for rel in ("scripts/release-tasks.sh", "scripts/verify-production-freeze.sh"):
    if "verify-sourcing-static-manifest-deployment-hotfix.py" not in read(rel):
        fail(f"{rel} does not execute the hotfix verifier")

release_notes = read("RELEASE_NOTES.md")
if "# 1.0.117 — Sourcing Static Manifest Deployment Hotfix\n" not in release_notes:
    fail("release notes are missing the Sourcing static-manifest hotfix section")
if "SESCCO MS 1.0.117 — Sourcing Static Manifest Deployment Hotfix" not in read("README.md"):
    fail("README current release identity mismatch")

print("Verified SESCCO MS 1.0.117 Sourcing static-manifest deployment hotfix: pre-collectstatic tests are manifest-independent, production manifest storage remains authoritative, and collected Sourcing assets are verified before cutover.")
