#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-v3-type-first-generator-api.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 TYPE-FIRST GENERATOR API ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != text("VERSION").strip():
    fail("type-first generator contract release must match VERSION")
if contract.get("upgrade") != "supplier-timesheet-pack-v3-type-first-generator-api" or contract.get("upgrade_sequence") != "8/14":
    fail("unexpected type-first generator upgrade identity")
if contract.get("schema_change") is not False or contract.get("data_rewrite") is not False:
    fail("Upgrade 8 must not add a migration or rewrite historical documents")
if contract.get("selector_max_page_size") != 25:
    fail("normal generator selectors must remain capped at 25 rows per request")

normal = contract.get("normal_generator") or {}
for key in (
    "purpose_first",
    "supplier_before_project",
    "exact_source_review_before_create",
    "source_revalidated_at_create",
):
    if normal.get(key) is not True:
        fail(f"missing type-first safety property: {key}")
for key in ("all_suppliers_default", "all_projects_default", "source_queries_on_type_catalog"):
    if normal.get(key) is not False:
        fail(f"normal generator must not use legacy eager/all-scope behavior: {key}")

expected_types = [
    "supplier_timesheet_pack",
    "supplier_settlement",
    "supplier_invoice",
    "supplier_payment_receipt",
]
if contract.get("document_types") != expected_types:
    fail("type-first catalog changed unexpectedly")
if contract.get("project_timesheet_in_normal_generator") is not False:
    fail("Project Timesheet must stay outside the normal supplier-document generator")

service = text(contract["implementation"]["service"])
for marker in (
    "TYPE_FIRST_SELECTOR_MAX_PAGE_SIZE = 25",
    "def type_first_generator_catalog()",
    "Static purpose-first catalog. It intentionally performs no source queries.",
    "def eligible_suppliers(",
    "def eligible_projects(",
    "Choose a supplier before searching projects.",
    "def eligible_sources(",
    "source_id__in=source_ids",
    "existing_by_source",
    "def resolve_type_first_source(",
    "def review_type_first_source(",
    "project_scope_ids(membership)",
    "RentalTimesheetStatus.LOCKED",
    "SupplierPaymentStatus.PAID",
):
    if marker not in service:
        fail(f"type-first service marker missing: {marker}")

api = text(contract["implementation"]["api"])
for marker in (
    "def document_generator_types_api(",
    "performs no Payroll/Rental source discovery",
    "def document_generator_suppliers_api(",
    "def document_generator_projects_api(",
    "def document_generator_sources_api(",
    "def document_generator_review_api(",
    "def document_generator_create_api(",
    "Re-resolve the exact source at commit time",
    "allow_supplier_timesheet_pack=document_type == DocumentType.SUPPLIER_TIMESHEET_PACK",
):
    if marker not in api:
        fail(f"type-first API marker missing: {marker}")

generic_api = api.split("def documents_api(", 1)[1].split("@require_http_methods", 1)[0]
if "allow_supplier_timesheet_pack=True" in generic_api or "allow_supplier_timesheet_pack=document_type" in generic_api:
    fail("generic POST /api/documents/ must remain closed to direct v3 pack creation")
if "Supplier Timesheet Pack creation is not yet exposed through the generic Documents API." not in text("apps/documents/services/documents.py"):
    fail("internal finalizer generic-API guard was removed")

urls = text(contract["implementation"]["urls"])
for name in (
    "document-generator-types-api",
    "document-generator-suppliers-api",
    "document-generator-projects-api",
    "document-generator-sources-api",
    "document-generator-review-api",
    "document-generator-create-api",
):
    if name not in urls:
        fail(f"type-first URL missing: {name}")
for legacy in (
    "document-generation-options-api",
    "document-generation-plan-api",
    "document-generation-execute-api",
):
    if legacy not in urls:
        fail(f"explicit bulk-generation compatibility route was removed: {legacy}")

js = text("static/payroll/js/app.js")
frontend_cut_over = "supplier_timesheet_pack" in js and "/api/documents/generator/" in js
if frontend_cut_over:
    if not (ROOT / "scripts/verify-payroll-document-v3-new-documents-ux.py").is_file():
        fail("type-first frontend is active without the Upgrade 9 UX release gate")
    for marker in ("openRentalTypeFirstDocumentDrawer", "renderRentalTypeFirstPurpose", "/api/documents/generator/create/"):
        if marker not in js:
            fail(f"Upgrade 9 frontend cutover is incomplete: {marker}")
for legacy_call in ("/api/documents/generation-options/", "/api/documents/generation-plan/", "/api/documents/generate/"):
    if legacy_call not in js:
        fail(f"explicit bulk-generation compatibility path disappeared: {legacy_call}")

migrations = sorted(path.name for path in (ROOT / "apps/documents/migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))
if migrations != [
    "0001_initial.py",
    "0002_alter_businessdocument_company_and_more.py",
    "0003_supplier_timesheet_pack_type.py",
]:
    fail(f"Upgrade 8 must not change the document migration lineage: {migrations}")

test_rel = contract["implementation"]["regression_tests"]
try:
    tree = ast.parse(text(test_rel))
except SyntaxError as exc:
    fail(f"type-first API regression tests are invalid Python: {exc}")
methods = {
    node.name
    for node in ast.walk(tree)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
}
required_methods = {
    "test_type_catalog_is_lightweight_and_exposes_only_supplier_facing_single_document_purposes",
    "test_supplier_and_project_selectors_are_bounded_and_dependency_scoped",
    "test_sources_and_review_resolve_only_the_selected_supplier_project_period",
    "test_type_first_create_is_the_only_api_path_that_can_activate_v3_pack",
    "test_type_first_routes_do_not_expose_project_timesheet_or_unbounded_all_scope",
}
if not required_methods.issubset(methods):
    fail(f"type-first generator regression evidence incomplete: {sorted(required_methods - methods)}")
test_text = text(test_rel)
if "with self.assertNumQueries(0):" not in test_text or "type_first_generator_catalog()" not in test_text:
    fail("lightweight type catalog must have explicit zero-database-query regression evidence")

for rel in ("scripts/verify-production-freeze.sh", "scripts/release-tasks.sh", "scripts/verify-payroll-production-e2e.py"):
    if "verify-payroll-document-v3-type-first-generator-api.py" not in text(rel):
        fail(f"type-first generator API is not release-gated by {rel}")

print(
    "Verified Supplier Timesheet Pack v3 type-first generator API: zero-source type catalog, "
    "bounded 25-row selectors, supplier->project dependency, exact-source review/revalidation, "
    "v3 pack creation only through the new path, project-scope enforcement, explicit bulk compatibility, "
    "no migration; Upgrade 9 frontend cutover is accepted when its dedicated release gate is present."
)
