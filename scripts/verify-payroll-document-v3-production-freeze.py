#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "merge/payroll-document-v3-production-freeze.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 PRODUCTION FREEZE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


if CONTRACT.get("release") != "1.0.117" or CONTRACT.get("upgrade_sequence") != "14/14":
    fail("final contract must be frozen at release 1.0.117 Upgrade 14/14")
if CONTRACT.get("status") != "production_frozen":
    fail("Supplier Timesheet Pack v3 is not marked production_frozen")
if CONTRACT.get("primary_timesheet_type") != "supplier_timesheet_pack":
    fail("v3 Supplier Timesheet Pack is not the frozen primary timesheet type")
if CONTRACT.get("document_schema_version") != "3.0":
    fail("final v3 schema version changed")
if CONTRACT.get("generic_documents_post_allows_v3") is not False:
    fail("generic Documents POST must remain closed to direct v3 pack creation")
if CONTRACT.get("type_first_generator_is_normal_creation_path") is not True:
    fail("type-first generator is not frozen as the normal creation path")
if CONTRACT.get("worker_export_creates_business_document") is not False:
    fail("worker-only export must remain derived from the immutable parent pack")
if CONTRACT.get("timesheet_pack_contains_commercial_values") is not False:
    fail("timesheet pack must remain operational and non-commercial")
if CONTRACT.get("financial_authority_requires_timesheet_pack") is not False:
    fail("financial authority must remain independent of document generation")
if CONTRACT.get("supplier_invoice_received_is_outbound") is not False:
    fail("Supplier Invoice Received must remain inbound-only")
if CONTRACT.get("supplier_acknowledgement_is_approval") is not False:
    fail("supplier acknowledgement must remain receipt-only")
if CONTRACT.get("legacy_v2_documents_remain_readable") is not True:
    fail("legacy v2 document compatibility cannot be removed at final freeze")
if CONTRACT.get("historical_rows_rewritten") is not False:
    fail("final freeze must not rewrite historical document rows")

for rel in CONTRACT.get("required_static_verifiers") or []:
    if not (ROOT / rel).is_file():
        fail(f"registered final verifier missing: {rel}")

models = text("apps/documents/models.py")
migration = text("apps/documents/migrations/0003_supplier_timesheet_pack_type.py")
finalizer = text("apps/documents/services/documents.py")
generator = text("apps/documents/services/type_first_generator.py")
printing = text("apps/documents/printing.py")
delivery = text("apps/documents/delivery.py")
reconciliation = text("apps/core/management/commands/merge_documents_management_report.py")
tests = text("apps/documents/tests/test_v3_production_freeze_acceptance.py")
release_tasks = text("scripts/release-tasks.sh")
production_freeze = text("scripts/verify-production-freeze.sh")
frontend_gate = text("scripts/verify-payroll-frontend.sh")
e2e_contract = json.loads(text("merge/payroll-production-e2e.json"))
e2e_verifier = text("scripts/verify-payroll-production-e2e.py")
release_candidate = json.loads(text("merge/release-candidate.json"))
migration_doc = text("docs/PAYROLL_DOCUMENT_V3_MIGRATION.md")
freeze_doc = text("docs/SUPPLIER_TIMESHEET_PACK_PRODUCTION_FREEZE.md")

require(models, 'SUPPLIER_TIMESHEET_PACK = "supplier_timesheet_pack"', "stored v3 document type disappeared")
require(migration, '"supplier_timesheet_pack"', "v3 stored-type migration no longer permits Supplier Timesheet Pack")
require(finalizer, "allow_supplier_timesheet_pack: bool = False", "generic v3 creation guard disappeared")
require(finalizer, "if normalized_type == DocumentType.SUPPLIER_TIMESHEET_PACK and not allow_supplier_timesheet_pack", "generic v3 creation is no longer fail-closed")
require(finalizer, "select_for_update()", "v3 finalization lost source-row serialization")
require(generator, "DocumentType.SUPPLIER_TIMESHEET_PACK", "type-first generator no longer exposes the v3 pack")
require(printing, "build_supplier_timesheet_pack_print_context", "full-pack renderer disappeared")
require(printing, "build_supplier_timesheet_pack_worker_print_context", "derived worker renderer disappeared")
require(delivery, 'SUPPLIER_DELIVERY_PRIMARY_TYPE = "supplier_timesheet_pack"', "supplier delivery no longer treats the v3 pack as primary")

# Final reconciliation must accept both generations of the qualified Rental Timesheet source
# while validating the stronger v3 bindings.
for needle, message in (
    ("validate_document_snapshot_for_type(document.document_type, document.snapshot)", "management reconciliation no longer validates document schema contracts"),
    ("document.document_type == DocumentType.RENTAL_TIMESHEET", "legacy supplier-timesheet reconciliation compatibility disappeared"),
    ("document.document_type == DocumentType.SUPPLIER_TIMESHEET_PACK", "v3 qualified-source reconciliation disappeared"),
    ('source_snapshot.get("id")', "v3 reconciliation no longer checks source id binding"),
    ("expected_source_fingerprint = hashlib.sha256(encoded).hexdigest()", "v3 reconciliation no longer checks source fingerprint binding"),
    ("v3 pack source fingerprint mismatch", "v3 reconciliation no longer fails closed on source-fingerprint drift"),
):
    require(reconciliation, needle, message)

for method in CONTRACT.get("final_acceptance_evidence") or []:
    require(tests, f"def {method}", f"final acceptance test evidence missing: {method}")

final_verifier = "scripts/verify-payroll-document-v3-production-freeze.py"
for source, label in (
    (release_tasks, "release tasks"),
    (production_freeze, "production freeze"),
    (frontend_gate, "Payroll frontend integration gate"),
):
    require(source, final_verifier.split("/", 1)[1], f"{label} does not run the final document-v3 freeze verifier")

if CONTRACT.get("runtime_test_label") not in (e2e_contract.get("runtime_test_labels") or []):
    fail("production-E2E runtime suite does not include the final v3 acceptance tests")
if final_verifier not in (e2e_contract.get("static_verifiers") or []):
    fail("production-E2E contract does not register the final v3 freeze verifier")
if not any(row.get("id") == "supplier-timesheet-pack-v3-production-freeze-acceptance" for row in e2e_contract.get("scenarios") or []):
    fail("production-E2E contract has no final v3 freeze acceptance scenario")
require(e2e_verifier, '"supplier-timesheet-pack-v3-production-freeze-acceptance"', "production-E2E verifier does not require the final v3 scenario")
require(e2e_verifier, '"apps.documents.tests.test_v3_production_freeze_acceptance"', "production-E2E verifier does not require the final runtime label")
require(e2e_verifier, '"scripts/verify-payroll-document-v3-production-freeze.py"', "production-E2E verifier does not require the final static gate")

if final_verifier not in (release_candidate.get("required_static_gates") or []):
    fail("release-candidate contract does not register the final v3 freeze verifier")
if CONTRACT.get("final_reconciliation_gate") not in (release_candidate.get("required_runtime_gates") or []):
    fail("release-candidate runtime gates do not include final document reconciliation")
scale_benchmark = "python manage.py supplier_timesheet_pack_scale_report --min-workers 250 --fail-on-limits"
if scale_benchmark not in (release_candidate.get("required_benchmark_gates") or []):
    fail("release-candidate benchmark gates do not include the 250-worker v3 scale report")

require(migration_doc, "Upgrade 14/14", "migration guide is not closed at Upgrade 14/14")
require(migration_doc, "production-frozen", "migration guide does not mark the v3 workflow production-frozen")
require(freeze_doc, "merge_documents_management_report --fail-on-errors", "production-freeze operator guide lost document reconciliation")
require(freeze_doc, "supplier_timesheet_pack_scale_report", "production-freeze operator guide lost scale acceptance")

print("Verified Supplier Timesheet Pack v3 Upgrade 14/14 production freeze, reconciliation closure and end-to-end acceptance wiring.")
