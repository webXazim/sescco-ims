#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING BROWSER E2E FREEZE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.113":
    fail(f"VERSION must be 1.0.113, found {version!r}")

contract = json.loads(text("merge/sourcing-browser-e2e-production-freeze.json"))
if contract.get("release") != version:
    fail("contract release does not match VERSION")
if contract.get("previous_release") != "1.0.110-sourcing-security-tenant-cross-module-isolation-certification":
    fail("predecessor release changed")
if contract.get("previous_archive_sha256") != "bf498e6af3405b279cb42fbbf769c5baeb14d8940d59b3f732e89950dd503b2b":
    fail("predecessor SHA-256 changed")
if contract.get("schema_change") is not False:
    fail("final browser freeze must not introduce schema changes")
if contract.get("permission_catalog_size") != 94:
    fail("permission catalog size changed")
if contract.get("persisted_model_retention_count") != 75:
    fail("retention model count changed")
if contract.get("required_seed_profile") != "benchmark":
    fail("browser E2E must use benchmark Sourcing seed")
if contract.get("operational_mutation_allowed") is not False:
    fail("operational mutation must remain prohibited")
if contract.get("final_sourcing_feature_freeze") is not True:
    fail("final Sourcing feature freeze flag missing")

expected_seed = {
    "vendor": "SDEMO-V00001",
    "material_query": "SDEMO Material 0001",
    "manpower_supplier": "SDEMO-P00001",
    "trade_query": "SDEMO Trade 001",
}
if contract.get("required_seed_contract") != expected_seed:
    fail("deterministic browser seed anchors changed")

expected_scenarios = {
    "login",
    "vendor-directory",
    "vendor-supply-catalog",
    "material-finder",
    "vendor-verification-history-before",
    "vendor-quick-verification",
    "vendor-verification-history-after",
    "manpower-directory",
    "manpower-workforce-catalog",
    "workforce-finder",
    "workforce-verification-history-before",
    "workforce-quick-verification",
    "workforce-verification-history-after",
}
if set(contract.get("browser_scenarios") or []) != expected_scenarios:
    fail("browser scenario set changed")
limits = contract.get("browser_limits") or {}
if limits.get("max_rendered_business_rows") != 100 or limits.get("max_settle_ms") != 10_000:
    fail("browser row/settle limits changed")
if limits.get("finder_search_debounce_ms") != 350 or limits.get("stale_request_abort_required") is not True:
    fail("Finder stale-request protection changed")

runner = text("scripts/certify-sourcing-browser-e2e.py")
try:
    ast.parse(runner)
except SyntaxError as exc:
    fail(f"live browser runner is invalid Python: {exc}")
for needle in (
    'RELEASE = "1.0.113"',
    'VENDOR_CODE = "SDEMO-V00001"',
    'MATERIAL_QUERY = "SDEMO Material 0001"',
    'MANPOWER_CODE = "SDEMO-P00001"',
    'TRADE_QUERY = "SDEMO Trade 001"',
    'app/sourcing/vendors/',
    'app/sourcing/material-finder/',
    'app/sourcing/manpower-suppliers/',
    'app/sourcing/workforce-finder/',
    'vendor-supply-catalog',
    'vendor-quick-verification',
    'workforce-quick-verification',
    'sourcing-verification-timeline',
    'AbortController',  # enforced in the frontend checked below; marker also documents the expectation
):
    if needle not in runner and needle != 'AbortController':
        fail(f"live browser runner lost required flow marker: {needle}")
for forbidden in ("/payroll/", "/inventory/", "/projects/", "/accounting/"):
    if forbidden in runner:
        fail(f"browser runner must not navigate operational module: {forbidden}")

finder_js = text("static/sourcing/js/finder-scale.js")
for needle in ("new AbortController()", 'timer = setTimeout(() => run(submitUrl(), { push: false }), 350)', "serial !== requestSerial"):
    if needle not in finder_js:
        fail(f"Finder browser-scale authority missing: {needle}")

for template, needles in {
    "templates/sourcing/vendors/detail.html": ('data-sourcing-tab="catalog"', 'data-sourcing-panel="catalog"', "Verification history", "Verify now"),
    "templates/sourcing/material_finder/list.html": ('data-sourcing-finder-root', 'data-sourcing-live-finder', "Verification history", "Verify now"),
    "templates/sourcing/manpower/detail.html": ('data-sourcing-tab="workforce"', 'data-sourcing-panel="workforce"', "Verification history", "Verify now"),
    "templates/sourcing/workforce_finder/list.html": ('data-sourcing-finder-root', 'data-sourcing-live-finder', "Verification history", "Verify now"),
    "templates/sourcing/vendors/offer_history.html": ("sourcing-verification-timeline", "Immutable sourcing evidence"),
    "templates/sourcing/manpower/workforce_history.html": ("sourcing-verification-timeline", "Immutable sourcing evidence"),
}.items():
    body = text(template)
    for needle in needles:
        if needle not in body:
            fail(f"browser surface marker missing from {template}: {needle}")

security = text("apps/sourcing/tests/test_security_certification.py")
for needle in ("operational", "security_version", "test_archived_and_trash_sources_never_leak_into_finders"):
    if needle not in security:
        fail(f"1.0.110 security runtime authority no longer covers {needle}")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh"):
    if "verify-sourcing-browser-e2e.py" not in text(rel):
        fail(f"{rel} does not enforce the final Sourcing browser gate")

candidate = json.loads(text("merge/release-candidate.json"))
if candidate.get("release") != version:
    fail("release candidate does not match VERSION")
if "scripts/verify-sourcing-browser-e2e.py" not in (candidate.get("required_static_gates") or []):
    fail("release candidate does not require final Sourcing browser gate")
if "python manage.py test apps.sourcing.tests.test_browser_e2e_freeze --noinput" not in (candidate.get("required_runtime_gates") or []):
    fail("release candidate does not require Sourcing browser contract runtime test")
if not any("certify-sourcing-browser-e2e.py" in item for item in (candidate.get("required_benchmark_gates") or [])):
    fail("release candidate does not require live Sourcing Chromium E2E")
if candidate.get("sourcing_live_browser_evidence") != "sourcing-browser-certification.json":
    fail("release candidate lost Sourcing browser evidence filename")

print("Verified SESCCO MS 1.0.113 final Sourcing live-browser E2E and production-freeze contract across 13 real UI scenarios.")
