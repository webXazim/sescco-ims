from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse


ROOT = Path(__file__).resolve().parents[3]
JS_PATH = ROOT / "static" / "payroll" / "js" / "app.js"
CSS_PATH = ROOT / "static" / "payroll" / "css" / "v2" / "pages" / "payroll.css"


def _function_body(source: str, name: str, next_marker: str) -> str:
    start = source.index(f"function {name}") if f"function {name}" in source else source.index(f"async function {name}")
    end = source.index(next_marker, start)
    return source[start:end]


class SupplierTimesheetPackV3NewDocumentsUxCutoverTests(SimpleTestCase):
    def setUp(self):
        self.js = JS_PATH.read_text(encoding="utf-8")
        self.css = CSS_PATH.read_text(encoding="utf-8")

    def test_rental_new_document_opens_purpose_first_without_heavy_scope_discovery(self):
        opener = _function_body(self.js, "openRentalTypeFirstDocumentDrawer", "\n\n  const rentalGeneratorTypes")
        self.assertIn("typeFirstGenerator:true", opener)
        self.assertIn("renderRentalTypeFirstPurpose()", opener)
        self.assertIn("/api/documents/generator/types/", self.js)
        self.assertNotIn("generation-options", opener)
        self.assertNotIn("generation-batches", opener)

    def test_purpose_catalog_contains_only_supplier_facing_business_actions(self):
        start = self.js.index("const rentalTypeFirstFallbackCatalog")
        end = self.js.index("function rentalTypeFirstTypeKey", start)
        catalog = self.js[start:end]
        for document_type in (
            "supplier_timesheet_pack",
            "supplier_settlement",
            "supplier_invoice",
            "supplier_payment_receipt",
        ):
            self.assertIn(document_type, catalog)
        self.assertNotIn("rental_timesheet", catalog)
        self.assertIn("Open Project Timesheets", self.js)
        self.assertIn("navigate('timesheets')", self.js)

    def test_scope_is_progressive_and_uses_bounded_dependency_selectors(self):
        scope = _function_body(self.js, "renderRentalTypeFirstScope", "\n\n  function rentalTypeFirstSummaryRows")
        self.assertIn("/api/documents/generator/suppliers/", scope)
        self.assertIn("/api/documents/generator/projects/", scope)
        self.assertIn("/api/documents/generator/sources/", scope)
        self.assertIn("supplier_code", scope)
        self.assertIn("project_id", scope)
        self.assertIn("autoLoad:true", scope)
        self.assertIn("page_size:'10'", self.js)
        self.assertIn("payload.suppliers||payload.projects", self.js)

    def test_review_and_create_use_type_first_endpoints_and_invoice_remains_multipart(self):
        self.assertIn("/api/documents/generator/review/", self.js)
        self.assertIn("/api/documents/generator/create/", self.js)
        execute = _function_body(self.js, "executeRentalTypeFirstDocument", "\n\n  async function openRentalTypeFirstDocumentDrawer")
        self.assertIn("appMultipartApi('/api/documents/generator/create/'", execute)
        self.assertIn("appApi('/api/documents/generator/create/'", execute)
        self.assertNotIn("appApi('/api/documents/'", execute)
        self.assertIn("review.existing", execute)

    def test_frontend_cutover_is_reachable_and_has_dedicated_breathing_layout(self):
        routing = _function_body(self.js, "openDocumentGenerateDrawer", "\n\n\n  async function createSupplierTimesheetStatementBatch")
        self.assertIn("if(state.workspace==='rental')return openRentalTypeFirstDocumentDrawer(preferredType);", routing)
        self.assertIn("ui-v2-payroll-document-drawer--type-first", self.css)
        self.assertIn("document-purpose-list", self.css)
        self.assertIn("document-type-first-review", self.css)
        self.assertEqual(reverse("documents:document-generator-types-api"), "/api/documents/generator/types/")
        self.assertEqual(reverse("documents:document-generator-create-api"), "/api/documents/generator/create/")
