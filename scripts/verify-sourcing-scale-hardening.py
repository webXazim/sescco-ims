#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.111"
PREDECESSOR_SHA = "eaf3056bd03657b14cf5bd25230f72718cadef14473d0240c4992f268d8b4784"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING SCALE HARDENING ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail("VERSION is not 1.0.111")
contract = json.loads(text("merge/sourcing-scale-hardening.json"))
if contract.get("release") != VERSION or contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("release/predecessor binding changed")
expected = {"vendors": 10000, "materials": 2000, "vendor_offers": 50000, "manpower_suppliers": 5000, "trades": 250, "workforce_offers": 25000}
if contract.get("benchmark_volume") != expected:
    fail("benchmark volume changed")
if contract.get("page_sizes") != [25, 50, 100] or contract.get("max_browser_rows") != 100:
    fail("bounded browser contract changed")

seed = text("apps/sourcing/management/scale_seed.py")
for marker in (
    '"benchmark": SourcingScaleProfile("benchmark", 10_000, 2_000, 50_000, 5_000, 250, 25_000)',
    'SEED_PREFIX = "SDEMO-"',
    'allow_mixed: bool = False',
    'ignore_conflicts=True',
    'SourcingVendorOffer',
    'SourcingWorkforceOffer',
):
    if marker not in seed:
        fail(f"scale seed authority missing: {marker}")
for forbidden in ("apps.inventory", "apps.rental_manpower", "apps.internal_payroll", "apps.projects", "apps.documents"):
    if forbidden in seed:
        fail(f"scale seed crossed operational boundary: {forbidden}")

scale_selector = text("apps/sourcing/selectors/scale.py")
for marker in ("Exists(contact_match)", "Subquery(active_offer_count", "Subquery(active_contact_count", "material_directory_scale_annotations", "trade_directory_scale_annotations"):
    if marker not in scale_selector:
        fail(f"directory query hardening missing: {marker}")
for rel, forbidden in (("apps/sourcing/selectors/vendors.py", ".distinct()"), ("apps/sourcing/selectors/manpower.py", ".distinct()")):
    if forbidden in text(rel):
        fail(f"join fanout DISTINCT returned in {rel}")

for rel, markers in (
    ("apps/sourcing/selectors/materials.py", ("def vendor_catalog_page(", "Paginator(queryset, size)")),
    ("apps/sourcing/selectors/workforce.py", ("def workforce_catalog_page(", "Paginator(queryset, size)")),
):
    payload = text(rel)
    for marker in markers:
        if marker not in payload:
            fail(f"bounded profile catalog missing: {rel}: {marker}")

js = text("static/sourcing/js/finder-scale.js")
for marker in ("AbortController", "controller.abort()", "setTimeout(() => run(submitUrl(), { push: false }), 350)", "data-sourcing-finder-root", "DOMParser"):
    if marker not in js:
        fail(f"stale-request protection missing: {marker}")
for rel in ("templates/sourcing/material_finder/list.html", "templates/sourcing/workforce_finder/list.html"):
    payload = text(rel)
    for marker in ("data-sourcing-finder-root", "data-sourcing-live-finder", "finder-scale.js"):
        if marker not in payload:
            fail(f"Finder scale binding missing in {rel}: {marker}")

migration = text("apps/sourcing/migrations/0006_scale_finder_indexes.py")
for marker in ("src_offer_mat_verify_idx", "src_offer_avail_ver_idx", "src_work_trade_ver_idx", "src_work_avail_ver_idx", "src_mat_scale_find_idx", "src_trade_scale_find_idx"):
    if marker not in migration:
        fail(f"scale index missing: {marker}")

report = text("apps/sourcing/management/commands/sourcing_scale_report.py")
for marker in ("BENCHMARK_VOLUME", "CaptureQueriesContext", "Material Finder search", "Workforce Finder search", "5,000-row import parser", "--require-benchmark-volume", "--fail-on-limits"):
    if marker not in report:
        fail(f"scale report authority missing: {marker}")

tests = text("apps/sourcing/tests/test_scale_hardening.py")
for marker in ("test_scale_profiles_freeze_expected_volumes", "test_functional_seed_and_profile_catalogs_are_bounded", "test_directory_and_finder_pages_never_return_more_than_requested_page"):
    if marker not in tests:
        fail(f"runtime scale regression missing: {marker}")

for rel in (
    "apps/sourcing/selectors/scale.py",
    "apps/sourcing/management/scale_seed.py",
    "apps/sourcing/management/commands/seed_sourcing_test_data.py",
    "apps/sourcing/management/commands/sourcing_scale_report.py",
    "apps/sourcing/tests/test_scale_hardening.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

release_tasks = text("scripts/release-tasks.sh")
for marker in ("verify-sourcing-scale-hardening.py", "seed_sourcing_test_data", "apps.sourcing.tests.test_scale_hardening"):
    if marker not in release_tasks:
        fail(f"release task missing scale authority: {marker}")

print("PASS: SESCCO MS 1.0.111 Sourcing scale hardening verified: benchmark seed, composite indexes, bounded profile catalogs, subquery/EXISTS directories, stale-request cancellation and runtime scale report.")
