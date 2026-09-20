#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "merge/payroll-document-v3-freeze.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 FREEZE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def sha256(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing frozen file: {rel}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("freeze release must match VERSION")
if contract.get("upgrade") != "rental-document-v3-contract-freeze" or contract.get("upgrade_sequence") != "1/14":
    fail("unexpected v3 migration stage")
if contract.get("state") != "freeze_only" or contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("contract-freeze stage must not change schema or rewrite data")
if contract.get("current_document_schema_version") != "2.0" or contract.get("target_document_schema_version") != "3.0":
    fail("document schema transition is not frozen at v2 -> v3")

baseline = contract.get("baseline_sha256") or {}
mutable_after_freeze = {
    "apps/documents/models.py",
    "apps/documents/services/documents.py",
    # Upgrade 8 adds purpose-first endpoints to api.py. The legacy API surface is
    # guarded structurally below so additive endpoints do not invalidate the freeze.
    "apps/documents/api.py",
    # Additive v3 renderer integration is allowed after the freeze, but the
    # legacy v2 markers below remain enforced so historical print behavior
    # cannot silently disappear during the staged cutover.
    "apps/documents/views.py",
    "apps/documents/urls.py",
    # Staged v3 UI upgrades intentionally replace the Rental Documents creation/register
    # experience. Legacy v2 backend/print/source authority remains structurally guarded.
    "static/payroll/js/app.js",
    "templates/documents/print.html",
}
for rel, expected in baseline.items():
    if rel in mutable_after_freeze:
        continue
    actual = sha256(rel)
    if actual != expected:
        fail(f"frozen pre-v3 authority changed unexpectedly: {rel} ({actual})")

models = text("apps/documents/models.py")
legacy_types = contract["legacy_v2"]["stored_document_types"]
for value in legacy_types:
    if f'"{value}"' not in models:
        fail(f"legacy v2 document type disappeared: {value}")
if 'SUPPLIER_TIMESHEET_PACK = "supplier_timesheet_pack"' in models:
    # Additive v3 stages may introduce the new type after this freeze. The legacy
    # choices above must still remain present and immutable.
    if 'DocumentType.SUPPLIER_TIMESHEET_PACK: "Supplier Monthly Timesheet Pack"' not in models:
        fail("v3 stored type exists without its production label")
for marker in (
    'raise NotSupportedError("Final business documents are immutable and cannot be updated.")',
    'raise NotSupportedError("Final business documents are immutable and cannot be deleted.")',
    'name="doc_source_type_uniq"',
    'name="doc_type_valid"',
):
    if marker not in models:
        fail(f"BusinessDocument immutability/identity guard changed: {marker}")

api = text("apps/documents/api.py")
for marker in (
    'def documents_api(request: HttpRequest) -> JsonResponse:',
    'def document_sources_api(request: HttpRequest) -> JsonResponse:',
    'def document_generation_options_api(request: HttpRequest) -> JsonResponse:',
    'def document_generation_plan_api(request: HttpRequest) -> JsonResponse:',
    'def document_generation_execute_api(request: HttpRequest) -> JsonResponse:',
    'def document_generation_batches_api(request: HttpRequest) -> JsonResponse:',
    'def batch_supplier_settlement_statements_api(request: HttpRequest) -> JsonResponse:',
    'def batch_supplier_timesheet_statements_api(request: HttpRequest) -> JsonResponse:',
    'def document_detail_api(request: HttpRequest, document_id) -> JsonResponse:',
):
    if marker not in api:
        fail(f"legacy v2 document API disappeared during additive v3 work: {marker}")
# The generic create path must stay closed to the v3 pack until the dedicated cutover path
# explicitly opts in; an additive generator endpoint must not silently widen legacy POST.
documents_api_start = api.find("def documents_api(request: HttpRequest) -> JsonResponse:")
documents_api_end = api.find("\n@require_http_methods", documents_api_start + 1)
documents_api_block = api[documents_api_start:documents_api_end if documents_api_end > 0 else len(api)]
if "allow_supplier_timesheet_pack=True" in documents_api_block:
    fail("generic /api/documents/ POST unexpectedly activates Supplier Timesheet Pack creation")

service = text("apps/documents/services/documents.py")
for marker in (
    'SUPPLIER_TIMESHEET_ALIAS = "supplier_timesheet"',
    'PROJECT_TIMESHEET_VARIANT = "project_timesheet"',
    'SUPPLIER_TIMESHEET_VARIANT = "supplier_timesheet"',
    'if period.status != RentalTimesheetStatus.LOCKED:',
    'source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{normalized_supplier_code}"',
    'snapshot["document_schema_version"] = LEGACY_DOCUMENT_SCHEMA_VERSION',
    'if verify_document_snapshot(existing):',
):
    if marker not in service:
        fail(f"legacy v2 source/finalization contract changed: {marker}")

# The current supplier-timesheet snapshot intentionally excludes commercial rate values.
start = service.find("def _supplier_timesheet_snapshot")
end = service.find("\ndef _settlement_snapshot", start)
if start < 0 or end < 0:
    fail("cannot locate supplier-timesheet snapshot builder")
supplier_snapshot = service[start:end]
for forbidden in ('"rate":', '"base":', '"gross":', '"net":', '"adjustment_earnings":', '"adjustment_deductions":'):
    if forbidden in supplier_snapshot:
        fail(f"supplier timesheet leaked commercial value: {forbidden}")

rental_models = text("apps/rental_manpower/models/timesheets.py")
for marker in (
    "class RentalTimesheetEntry(CompanyOwnedModel):",
    "work_date = models.DateField()",
    'regular_hours = hours_field(default=Decimal("0"))',
    "class RentalTimesheetOvertime(CompanyOwnedModel):",
    'models.UniqueConstraint(fields=("period", "worker"), name="rntl_ts_ot_worker_uniq")',
):
    if marker not in rental_models:
        fail(f"Rental timesheet granularity authority changed: {marker}")
if "work_date = models.DateField()" in rental_models[rental_models.find("class RentalTimesheetOvertime"):]:
    fail("daily overtime authority appeared without an explicit timesheet-domain upgrade")


views = text("apps/documents/views.py")
for marker in (
    'document.document_type == DocumentType.RENTAL_TIMESHEET',
    'document_label = "Supplier Timesheet Statement"',
    'document_label = "Project Timesheet"',
    'render(',
    '"documents/print.html"',
):
    if marker not in views:
        fail(f"legacy v2 print-view behavior changed: {marker}")

print_template = text("templates/documents/print.html")
for marker in (
    "document.document_type == 'salary_slip'",
    "document.document_type == 'internal_timesheet'",
    "document.document_type == 'rental_timesheet'",
    "snapshot.document_variant == 'supplier_timesheet'",
    "Supplier Timesheet Statement",
    "Project Timesheet",
    "document.document_type == 'supplier_settlement'",
    "document.document_type == 'supplier_payment_receipt'",
):
    if marker not in print_template:
        fail(f"legacy v2 print template behavior changed: {marker}")

urls = text("apps/documents/urls.py")
for route in contract.get("protected_routes") or []:
    route_literal = route.lstrip("/")
    if f'path("{route_literal}"' not in urls:
        fail(f"protected document route changed or disappeared: {route}")

migrations_dir = ROOT / "apps/documents/migrations"
actual_migrations = sorted(
    f"apps/documents/migrations/{path.name}"
    for path in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.py")
)
frozen_lineage = contract.get("document_migration_lineage") or []
if actual_migrations[: len(frozen_lineage)] != frozen_lineage:
    fail(f"frozen v2 document migration lineage changed: {actual_migrations}")
for rel in frozen_lineage:
    expected = baseline.get(rel)
    if expected and sha256(rel) != expected:
        fail(f"frozen v2 migration changed: {rel}")

production = json.loads(text("merge/payroll-document-production.json"))
if production.get("document_schema_version") != "2.0":
    fail("current production document contract stopped declaring schema v2")
if production.get("supplier_document_workflow", {}).get("supplier_timesheet_source") != "locked_project_timesheet_supplier_scope":
    fail("current supplier-timesheet source authority changed")

freeze_runner = text("scripts/verify-production-freeze.sh")
release_tasks = text("scripts/release-tasks.sh")
for rel, payload in (
    ("scripts/verify-production-freeze.sh", freeze_runner),
    ("scripts/release-tasks.sh", release_tasks),
):
    if "verify-payroll-document-v3-freeze.py" not in payload:
        fail(f"v3 contract freeze is not enforced by {rel}")

print(
    "Verified Rental document v3 legacy freeze: immutable v2 history, locked-timesheet authority, "
    "daily regular/monthly OT granularity, public routes and frozen v2 migration lineage remain protected through additive v3 upgrades."
)
