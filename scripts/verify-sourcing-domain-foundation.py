#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.114"
PREDECESSOR_SHA = "ee87fc1253b800e1f4a336cae00283160d3379b3d73f1b6efd6678014cf56e38"
FORBIDDEN = ("inventory", "projects", "internal_payroll", "rental_manpower", "documents", "data_exchange")


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING FOUNDATION ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")
contract = json.loads(text("merge/sourcing-domain-foundation.json"))
if contract.get("release") != VERSION:
    fail("Sourcing contract release mismatch")
if contract.get("predecessor", {}).get("archive_sha256") != PREDECESSOR_SHA:
    fail("1.0.98 predecessor checksum changed")
if contract.get("schema_change") is not True:
    fail("1.0.114 must preserve the Sourcing schema foundation")
if contract.get("module_access_enabled") is not True:
    fail("1.0.114 must enable Sourcing only through the explicit permission cutover")
if contract.get("permission_cutover_contract") != "merge/sourcing-access-control.json":
    fail("Sourcing foundation is not bound to the 1.0.114 permission cutover contract")
if contract.get("payroll_formula_change") is not False or contract.get("inventory_quantity_formula_change") is not False:
    fail("Sourcing foundation must not alter Payroll or Inventory formulas")

settings = text("config/settings/base.py")
if '"apps.sourcing.apps.SourcingConfig"' not in settings:
    fail("Sourcing app is not registered")
urls = text("config/urls.py")
if 'path("app/sourcing/", include("apps.sourcing.urls"))' not in urls:
    fail("Sourcing URL namespace is not registered")
audit = text("apps/core/models/audit.py")
if 'SOURCING = "sourcing", "Sourcing"' not in audit:
    fail("Sourcing audit area is missing")
modules = text("apps/accounts/modules.py")
for marker in (
    'SOURCING = "sourcing"',
    'if value is PlatformModule.SOURCING:',
    'membership_has_any_sourcing_access',
    'normalized.startswith("/app/sourcing/")',
    'return "sourcing:home"',
):
    if marker not in modules:
        fail(f"permission-gated module registration missing: {marker}")

app_source = "\n".join(
    text(rel)
    for rel in (
        "apps/sourcing/models/base.py",
        "apps/sourcing/models/vendors.py",
        "apps/sourcing/models/manpower.py",
        "apps/sourcing/models/settings.py",
        "apps/sourcing/checks.py",
        "apps/sourcing/isolation.py",
    )
)
for forbidden in FORBIDDEN:
    for prefix in (f"from apps.{forbidden}", f"import apps.{forbidden}"):
        if prefix in app_source:
            fail(f"Sourcing source imports operational app {forbidden}")

migration = text("apps/sourcing/migrations/0001_sourcing_domain_foundation.py")
for forbidden in FORBIDDEN:
    if f'to="{forbidden}.' in migration or f"to='{forbidden}." in migration:
        fail(f"Sourcing migration contains operational FK to {forbidden}")
for marker in (
    'name="SourcingVendor"',
    'name="SourcingMaterial"',
    'name="SourcingVendorOffer"',
    'name="SourcingVendorOfferRevision"',
    'name="SourcingManpowerSupplier"',
    'name="SourcingTrade"',
    'name="SourcingWorkforceOffer"',
    'name="SourcingWorkforceOfferRevision"',
    'name="SourcingSettings"',
):
    if marker not in migration:
        fail(f"Sourcing foundation migration missing {marker}")

checks = text("apps/sourcing/checks.py")
for marker in ("sourcing.E001", "sourcing.E002", "FORBIDDEN_OPERATIONAL_APP_LABELS"):
    if marker not in checks:
        fail(f"Sourcing isolation system check missing: {marker}")

for rel in (
    "apps/sourcing/models/base.py",
    "apps/sourcing/models/vendors.py",
    "apps/sourcing/models/manpower.py",
    "apps/sourcing/models/settings.py",
    "apps/sourcing/checks.py",
    "apps/sourcing/views.py",
    "apps/sourcing/tests/test_domain_foundation.py",
    "apps/sourcing/migrations/0001_sourcing_domain_foundation.py",
    "apps/core/migrations/0006_sourcing_audit_area.py",
):
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"invalid Python in {rel}: {exc}")

models_vendor = text("apps/sourcing/models/vendors.py")
models_manpower = text("apps/sourcing/models/manpower.py")
for marker in (
    "class SourcingVendorOfferRevision",
    "ImmutableSourcingRevisionManager",
    "Sourcing offer revisions are immutable.",
):
    if marker not in models_vendor:
        fail(f"Vendor reference-history immutability missing: {marker}")
for marker in (
    "class SourcingWorkforceOfferRevision",
    "ImmutableSourcingRevisionManager",
    "Sourcing workforce revisions are immutable.",
):
    if marker not in models_manpower:
        fail(f"Workforce reference-history immutability missing: {marker}")

if "1.0.114" not in text("docs/SOURCING_DOMAIN_FOUNDATION.md"):
    fail("Sourcing foundation guide is not version-bound")

print("PASS: SESCCO MS 1.0.114 independent Sourcing Directory foundation remains operationally isolated and is exposed only through explicit persisted permissions.")
