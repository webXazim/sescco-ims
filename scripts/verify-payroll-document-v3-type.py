#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-type.json"
FREEZE = ROOT / "merge/payroll-document-v3-freeze.json"
AGGREGATOR = ROOT / "merge/payroll-document-v3-aggregator.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 TYPE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def sha256(rel: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / rel).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("v3 type contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-type-and-schema-foundation" or contract.get("upgrade_sequence") != "2/14":
    fail("unexpected v3 type upgrade identity")
if contract.get("state") != "additive_foundation_only" or contract.get("schema_change") is not True or contract.get("data_rewrite") is not False:
    fail("stage 2 must be an additive schema-only foundation with no data rewrite")
if contract.get("legacy_schema_version") != "2.0" or contract.get("new_schema_version") != "3.0":
    fail("schema versions must remain v2 legacy and v3 pack")

models = text("apps/documents/models.py")
for marker in (
    'SUPPLIER_TIMESHEET_PACK = "supplier_timesheet_pack", "Supplier Timesheet Pack"',
    'DocumentType.SUPPLIER_TIMESHEET_PACK: "Supplier Monthly Timesheet Pack"',
    'validate_document_snapshot_for_type(self.document_type, self.snapshot)',
    'name="doc_type_valid"',
):
    if marker not in models:
        fail(f"BusinessDocument v3 type foundation missing: {marker}")
for value in freeze["legacy_v2"]["stored_document_types"]:
    if f'"{value}"' not in models:
        fail(f"legacy stored type disappeared: {value}")

schema = text("apps/documents/schema.py")
for marker in (
    'LEGACY_DOCUMENT_SCHEMA_VERSION = "2.0"',
    'SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION = "3.0"',
    'SUPPLIER_TIMESHEET_PACK_TYPE = "supplier_timesheet_pack"',
    'def validate_supplier_timesheet_pack_snapshot',
    'Supplier Timesheet Pack source must be a Locked Rental Timesheet.',
    'cannot contain daily overtime; overtime authority is monthly per worker.',
    'SUPPLIER_TIMESHEET_PACK_FORBIDDEN_KEYS',
    '"rate"',
    '"payable"',
):
    if marker not in schema:
        fail(f"v3 snapshot foundation missing: {marker}")

migration_rel = contract["migration"]
migration = text(migration_rel)
for marker in (
    '("documents", "0002_alter_businessdocument_company_and_more")',
    'migrations.RemoveConstraint(',
    'migrations.AlterField(',
    'migrations.AddConstraint(',
    '"supplier_timesheet_pack"',
    'name="doc_type_valid"',
):
    if marker not in migration:
        fail(f"v3 additive migration missing: {marker}")
for forbidden in ("RunPython", "RunSQL", "DeleteModel", "RemoveField"):
    if forbidden in migration:
        fail(f"v3 type migration must not rewrite/remove production data: {forbidden}")

# Stage 1 migrations are permanent evidence and must not change as the additive migration is added.
baseline = freeze.get("baseline_sha256") or {}
for rel in freeze.get("document_migration_lineage") or []:
    expected = baseline.get(rel)
    if not expected or sha256(rel) != expected:
        fail(f"frozen v2 migration changed: {rel}")
actual_migrations = sorted(path.name for path in (ROOT / "apps/documents/migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))
if actual_migrations != ["0001_initial.py", "0002_alter_businessdocument_company_and_more.py", "0003_supplier_timesheet_pack_type.py"]:
    fail(f"unexpected current document migration lineage: {actual_migrations}")

service = text("apps/documents/services/documents.py")
for marker in (
    'SUPPLIER_TIMESHEET_ALIAS = "supplier_timesheet"',
    'SUPPLIER_TIMESHEET_VARIANT = "supplier_timesheet"',
    'requested_type = DocumentType.RENTAL_TIMESHEET',
    'document_variant = SUPPLIER_TIMESHEET_VARIANT',
    'snapshot["document_schema_version"] = LEGACY_DOCUMENT_SCHEMA_VERSION',
    'DocumentType.SUPPLIER_TIMESHEET_PACK: ("document.supplier_timesheet_pack", "STP-")',
):
    if marker not in service:
        fail(f"legacy-v2 compatibility or v3 reservation missing: {marker}")
# Stage 2 originally reserves the type without a generator. Once Upgrade 3 is
# present, internal source dispatch may activate only with the authoritative aggregator contract.
load_start = service.find("def _load_source")
load_end = service.find("\ndef _prefix", load_start)
if load_start < 0 or load_end < 0:
    fail("cannot locate document source dispatcher")
load_block = service[load_start:load_end]
aggregator_active = AGGREGATOR.is_file()
if "DocumentType.SUPPLIER_TIMESHEET_PACK" in load_block:
    if not aggregator_active:
        fail("v3 pack generation was activated before the v3 aggregator contract exists")
    if "build_supplier_timesheet_pack_snapshot" not in load_block:
        fail("v3 pack dispatch bypasses the authoritative aggregator")

selectors = text("apps/documents/selectors/documents.py")
for marker in (
    'DocumentType.SUPPLIER_TIMESHEET_PACK], source_id__in=timesheet_ids',
    'Q(document_type=DocumentType.SUPPLIER_TIMESHEET_PACK)',
    'legacy_supplier_timesheet_count',
    'v3_supplier_timesheet_count',
    'type_counts.pop(DocumentType.SUPPLIER_TIMESHEET_PACK, None)',
):
    if marker not in selectors:
        fail(f"staged selector compatibility missing: {marker}")

api = text("apps/documents/api.py")
js = text("static/payroll/js/app.js")
if "supplier_timesheet_pack" in js and not (ROOT / "scripts/verify-payroll-document-v3-new-documents-ux.py").is_file():
    fail("frontend creation UI is active without the planned Upgrade 9 release gate")
generic_api = api.split("def documents_api(", 1)[1].split("@require_http_methods", 1)[0]
if "allow_supplier_timesheet_pack=True" in generic_api:
    fail("generic Documents API must remain closed to direct v3 pack creation")
if aggregator_active and "Supplier Timesheet Pack creation is not yet exposed through the generic Documents API." not in text("apps/documents/services/documents.py"):
    fail("v3 internal finalizer guard was removed")

freeze_runner = text("scripts/verify-production-freeze.sh")
release_tasks = text("scripts/release-tasks.sh")
production_e2e = text("scripts/verify-payroll-production-e2e.py")
for rel, payload in (
    ("scripts/verify-production-freeze.sh", freeze_runner),
    ("scripts/release-tasks.sh", release_tasks),
    ("scripts/verify-payroll-production-e2e.py", production_e2e),
):
    if "verify-payroll-document-v3-type.py" not in payload:
        fail(f"v3 type foundation is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack v3 type/schema foundation: additive stored type, safe constraint migration, "
    "v2 compatibility, locked-source/monthly-OT schema guards, no commercial leakage and no premature generator/UI activation."
)
