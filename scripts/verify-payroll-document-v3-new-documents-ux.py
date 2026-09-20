#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/payroll/css/v2/pages/payroll.css").read_text(encoding="utf-8")
URLS = (ROOT / "apps/documents/urls.py").read_text(encoding="utf-8")
TESTS = (ROOT / "apps/documents/tests/test_v3_new_documents_ux_cutover.py").read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 NEW DOCUMENTS UX ERROR: {message}")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


for needle, message in (
    ("supplier_timesheet_pack:{label:'Supplier Timesheet',code:'ST'}", "new Supplier Timesheet UI metadata is missing"),
    ("const rentalTypeFirstFallbackCatalog", "purpose-first catalog is missing"),
    ("typeFirstGenerator:true", "Rental drawer is not marked as type-first"),
    ("renderRentalTypeFirstPurpose()", "purpose-first first screen is missing"),
    ("/api/documents/generator/types/", "lightweight type catalog is not used"),
    ("/api/documents/generator/suppliers/", "bounded supplier selector is not used"),
    ("/api/documents/generator/projects/", "dependency-scoped project selector is not used"),
    ("/api/documents/generator/sources/", "bounded source selector is not used"),
    ("/api/documents/generator/review/", "exact-source review endpoint is not used"),
    ("/api/documents/generator/create/", "type-first creation endpoint is not used"),
    ("Open Project Timesheets", "Project Timesheet routing guidance is missing"),
    ("navigate('timesheets')", "Project Timesheet is not routed back to its operational workspace"),
):
    require(JS, needle, message)

catalog = JS[JS.index("const rentalTypeFirstFallbackCatalog"):JS.index("function rentalTypeFirstTypeKey")]
for required_type in ("supplier_timesheet_pack", "supplier_settlement", "supplier_invoice", "supplier_payment_receipt"):
    require(catalog, required_type, f"purpose catalog lost {required_type}")
if "rental_timesheet" in catalog:
    fail("Project Timesheet must not be a supplier-facing New Document purpose")

opener_start = JS.index("async function openRentalTypeFirstDocumentDrawer")
opener_end = JS.index("\n\n  const rentalGeneratorTypes", opener_start)
opener = JS[opener_start:opener_end]
if "generation-options" in opener or "generation-batches" in opener:
    fail("opening the new Rental document drawer still triggers heavy legacy scope/batch discovery")

routing_start = JS.index("async function openDocumentGenerateDrawer")
routing_end = JS.index("async function createSupplierTimesheetStatementBatch", routing_start)
routing = JS[routing_start:routing_end]
require(routing, "if(state.workspace==='rental')return openRentalTypeFirstDocumentDrawer(preferredType);", "Rental New Document still opens the legacy checkbox generator")

execute_start = JS.index("async function executeRentalTypeFirstDocument")
execute_end = JS.index("async function openRentalTypeFirstDocumentDrawer", execute_start)
execute = JS[execute_start:execute_end]
require(execute, "appMultipartApi('/api/documents/generator/create/'", "supplier invoice does not use the type-first multipart create endpoint")
require(execute, "review.existing", "existing final documents are not duplicate-safe")
if "appApi('/api/documents/'" in execute:
    fail("type-first creation fell back to the generic Documents create endpoint")

for needle in ("ui-v2-payroll-document-drawer--type-first", "document-purpose-list", "document-type-first-review"):
    require(CSS, needle, f"missing type-first layout hook: {needle}")
for route in ("document-generator-types-api", "document-generator-suppliers-api", "document-generator-projects-api", "document-generator-sources-api", "document-generator-review-api", "document-generator-create-api"):
    require(URLS, route, f"type-first route disappeared: {route}")
for method in (
    "test_rental_new_document_opens_purpose_first_without_heavy_scope_discovery",
    "test_purpose_catalog_contains_only_supplier_facing_business_actions",
    "test_scope_is_progressive_and_uses_bounded_dependency_selectors",
    "test_review_and_create_use_type_first_endpoints_and_invoice_remains_multipart",
    "test_frontend_cutover_is_reachable_and_has_dedicated_breathing_layout",
):
    require(TESTS, f"def {method}", f"regression evidence missing: {method}")

print("Verified Supplier Timesheet Pack v3 purpose-first New Documents UX cutover.")
