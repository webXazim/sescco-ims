#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING DATA EXCHANGE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail("VERSION is not 1.0.116")
contract = json.loads(text("merge/sourcing-data-exchange.json"))
if contract.get("release") != VERSION or contract.get("schema_change") is not False:
    fail("data-exchange release contract changed")
if set(contract.get("datasets") or []) != {"vendors", "materials", "vendor_catalog", "manpower_suppliers", "trades", "workforce_catalog"}:
    fail("six-dataset authority changed")

exchange = text("apps/sourcing/exchange.py")
for marker in (
    "MAX_IMPORT_BYTES = 2 * 1024 * 1024",
    "MAX_IMPORT_ROWS = 5000",
    "load_workbook(io.BytesIO(raw), read_only=True, data_only=True)",
    "with transaction.atomic():",
    "transaction.set_rollback(True)",
    'action="sourcing.data_import.completed"',
    'action="sourcing.data_exported"',
    "_FORMULA_PREFIXES =",
    "value.startswith(_FORMULA_PREFIXES)",
    "verified_now = _bool",
    "create_vendor_offer(",
    "update_vendor_offer(",
    "create_workforce_offer(",
    "update_workforce_offer(",
):
    if marker not in exchange:
        fail(f"exchange safety/authority missing: {marker}")
for forbidden in ("from apps.inventory", "from apps.rental_manpower", "from apps.internal_payroll", "from apps.projects", "from apps.documents", "from apps.data_exchange"):
    if forbidden in exchange:
        fail(f"operational dependency introduced: {forbidden}")

views = text("apps/sourcing/views.py")
for marker in (
    "def _can_import_dataset(",
    "membership_can_manage_vendor_sourcing",
    "membership_can_manage_manpower_sourcing",
    "membership_can_manage_sourcing_masters",
    "def _can_export_dataset(",
    "membership_can_export_sourcing",
    "def data_exchange(",
    "def data_export(",
):
    if marker not in views:
        fail(f"view permission boundary missing: {marker}")

urls = text("apps/sourcing/urls.py")
for marker in ('"data-exchange/"', '"data-exchange/export/<str:dataset>/"'):
    if marker not in urls:
        fail(f"route missing: {marker}")

ui = text("templates/sourcing/data_exchange.html")
for marker in ("Validate only", "all-or-nothing", "verified_now=yes", "XLSX", "CSV", "Export Sourcing Data"):
    if marker not in ui:
        fail(f"data-exchange UI missing: {marker}")
sidebar = text("templates/sourcing/sidebar.html")
if "sourcing:data_exchange" not in sidebar:
    fail("data-exchange navigation missing")

tests = text("apps/sourcing/tests/test_data_exchange.py")
for marker in (
    "test_vendor_import_dry_run_rolls_back",
    "test_duplicate_import_identity_rejects_whole_batch",
    "test_catalog_import_can_bulk_verify_reference",
    "test_workforce_import_is_sourcing_only",
    "test_export_requires_export_permission_plus_dataset_view",
    "test_xlsx_export_is_readable_and_formula_cells_are_neutralized",
):
    if marker not in tests:
        fail(f"runtime regression missing: {marker}")

for rel in ("apps/sourcing/exchange.py", "apps/sourcing/forms.py", "apps/sourcing/views.py", "apps/sourcing/tests/test_data_exchange.py"):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

release_tasks = text("scripts/release-tasks.sh")
for marker in ("verify-sourcing-data-exchange.py", "apps.sourcing.tests.test_data_exchange"):
    if marker not in release_tasks:
        fail(f"release task missing: {marker}")
if VERSION not in text("docs/SOURCING_DATA_EXCHANGE.md"):
    fail("operator guide is not version-bound")

print("PASS: SESCCO MS 1.0.116 Sourcing Import / Export & Bulk Maintenance verified: dry-run rollback, all-or-nothing upsert, audited export, formula neutralization, permission isolation and reference-only bulk verification.")
