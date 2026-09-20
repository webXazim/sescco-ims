#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/payroll-document-production.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT PRODUCTION ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
if contract.get("release") != "1.0.117":
    fail("document production contract is not frozen at 1.0.117")
if len(contract.get("document_types") or []) != 7:
    fail("all seven Payroll document types must remain covered")
print_contract = contract.get("print_contract") or {}
if not print_contract.get("headpad_first_page_only") or not print_contract.get("plain_continuation_pages"):
    fail("print contract must keep the company headpad on page one and use plain continuation pages")
for key in ("native_first_page_preview", "preview_iframe_disabled", "full_print_opens_separately"):
    if print_contract.get(key) is not True:
        fail(f"production preview contract changed: {key}")
workflow = contract.get("supplier_invoice_workflow") or {}
for key in (
    "settlement_statement_generated_by_sescco", "supplier_invoice_received_record",
    "supplier_invoice_attachment_required", "supplier_invoice_attachment_hash_verified",
    "supplier_payment_requires_invoice_before_first_payment",
    "payment_payable_uses_invoice_total_including_vat", "supplier_payment_advice_generated_by_sescco",
    "batch_settlement_statements", "batch_supplier_timesheets",
):
    if workflow.get(key) is not True:
        fail(f"supplier invoice workflow guarantee changed: {key}")
if workflow.get("direction") != "supplier_to_sescco" or workflow.get("sescco_generates_supplier_tax_invoice") is not False:
    fail("supplier invoice direction must remain Supplier -> SESCCO, not buyer-issued")
if workflow.get("schema_change") is not False:
    fail("supplier invoice-received hotfix must not add a database schema change")
supplier_docs = contract.get("supplier_document_workflow") or {}
for key in (
    "project_timesheet_internal", "supplier_timesheet_statement", "supplier_timesheet_excludes_commercial_rates",
    "batch_supplier_timesheets", "supplier_settlement_statement", "supplier_invoice_received",
    "supplier_payment_advice", "separate_document_per_supplier_project_period", "stored_document_types_unchanged",
):
    if supplier_docs.get(key) is not True:
        fail(f"supplier document workflow guarantee changed: {key}")
if supplier_docs.get("supplier_timesheet_source") != "locked_project_timesheet_supplier_scope":
    fail("Supplier Timesheet Statement source authority changed")
if supplier_docs.get("schema_change") is not False:
    fail("supplier document expansion must remain schema-free")

asset_rel = contract["supplier_invoice_letterhead"]["asset"]
asset = ROOT / asset_rel
if not asset.is_file():
    fail("SESCCO supplier invoice letterhead asset is missing")
payload = asset.read_bytes()
if hashlib.sha256(payload).hexdigest() != contract["supplier_invoice_letterhead"]["sha256"]:
    fail("SESCCO supplier invoice letterhead hash changed")
if payload[:8] != b"\x89PNG\r\n\x1a\n":
    fail("SESCCO supplier invoice letterhead is not PNG")
size = [int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")]
if size != contract["supplier_invoice_letterhead"]["pixel_size"]:
    fail(f"SESCCO letterhead pixel size changed: {size}")

service = text("apps/documents/services/documents.py")
schema = text("apps/documents/schema.py")
if 'LEGACY_DOCUMENT_SCHEMA_VERSION = "2.0"' not in schema:
    fail("legacy document schema version is no longer pinned to v2")
for marker in (
    'SESCCO_COMPANY_DOCUMENT_HEADPAD = "apps/documents/assets/sescco-company-document-headpad-v2.png"',
    'SESCCO_SUPPLIER_INVOICE_LETTERHEAD = SESCCO_COMPANY_DOCUMENT_HEADPAD',
    'title = f"Supplier Invoice Received · {entity_name}"',
    'title = f"Supplier Settlement Statement · {entity_name}"',
    'title = f"Supplier Payment Advice · {entity_name}"',
    'SUPPLIER_TIMESHEET_ALIAS = "supplier_timesheet"',
    'def _supplier_timesheet_snapshot(period: RentalTimesheetPeriod, *, supplier_code: str)',
    'source_model = f"rental_manpower.rentaltimesheetperiod:supplier:{normalized_supplier_code}"',
    "title = f\"Supplier Timesheet Statement · {entity_name} · {snapshot['project']['name']}\"",
    'key, prefix = "document.supplier_timesheet", "STS-"',
    'branding_mode = "letterhead"',
    'snapshot["invoice"]["total_in_words"] = money_to_words',
    '"attachment": invoice.get("attachment")',
    '"supplier_invoice_number": invoice_doc.external_reference if invoice_doc else ""',
    'snapshot["document_schema_version"] = LEGACY_DOCUMENT_SCHEMA_VERSION',
    'snapshot["invoice"]["total_in_words"] = money_to_words',
    'DocumentType.SUPPLIER_PAYMENT_RECEIPT',
):
    if marker not in service:
        fail(f"document service lost production marker: {marker}")

reconciliation = text("apps/core/management/commands/merge_documents_management_report.py")
for marker in (
    'supplier_timesheet_base = "rental_manpower.rentaltimesheetperiod"',
    'base_source_model, separator, source_qualifier = source_identity.partition(":")',
    'source_model = django_apps.get_model(app_label, model_name)',
    'source_qualifier.lower().startswith("supplier:")',
    'snapshot.get("document_variant") != "supplier_timesheet"',
    'snapshot_supplier_code != supplier_code',
    'document.entity_reference or ""',
    'unsupported qualified source model',
):
    if marker not in reconciliation:
        fail(f"Documents/Management reconciliation lost supplier-timesheet compound-source support: {marker}")

views = text("apps/documents/views.py")
for marker in ('descriptor.get("package_path")', 'apps" / "documents" / "assets', 'digest.hexdigest() != descriptor.get("sha256")', 'return static("payroll/assets/sescco-company-document-headpad-v2.png")', 'def document_source_attachment', 'Supplier invoice attachment integrity verification failed.'):
    if marker not in views:
        fail(f"historical packaged-brand asset guard missing: {marker}")

api = text("apps/documents/api.py")
for marker in (
    'page_size = min(25, max(1, int(request.GET.get("page_size", 10))))',
    'stop = start + page_size + 1',
    'requires_search = document_type in {DocumentType.SALARY_SLIP, DocumentType.SALARY_PAYMENT_RECEIPT}',
    'Choose a document type before searching source records.',
    'source_id=OuterRef("pk")',
    '.annotate(_finalized=Exists(existing))',
    'Supplier invoice file is required.',
    'supplier-invoices/{request.company.id}/',
    'def batch_supplier_settlement_statements_api',
    'def batch_supplier_timesheet_statements_api',
    'SUPPLIER_TIMESHEET_ALIAS',
    'RentalTimesheetEntry.objects.for_company(request.company)',
    'source_id=OuterRef("period_id")',
    'entity_reference=OuterRef("supplier_code")',
):
    if marker not in api:
        fail(f"bounded document source lookup marker missing: {marker}")

js = text("static/payroll/js/app.js")
for marker in (
    "function documentSourceTypesForWorkspace()",
    "function cancelDocumentSourceRequest()",
    "function setupDocumentSourceCombobox()",
    "key:'document-source',endpoint:'/api/documents/sources/'",
    "function documentNativePreview(doc)",
    "document-native-preview",
    "supplier_invoice:{label:'Supplier Invoice Received',code:'IR'}",
    "supplier_settlement:{label:'Supplier Settlement Statement',code:'SS'}",
    "supplier_payment_receipt:{label:'Supplier Payment Advice',code:'PA'}",
    "supplier_timesheet:{label:'Supplier Timesheet Statement',code:'ST'}",
    "rental_timesheet:{label:'Project Timesheet',code:'PT'}",
    'name="document-invoice-file"',
    "appMultipartApi('/api/documents/'",
    "data-document-batch-settlements",
    "function createSupplierSettlementStatementBatch()",
    "function createSupplierTimesheetStatementBatch()",
    "data-document-batch-timesheets",
    "if(source.supplierCode)body.supplier_code=source.supplierCode",
    "return `${periodMonths[Math.max(0,Math.min(11,month-1))]} ${year}`;",
):
    if marker not in js:
        fail(f"document finalization UI lost bounded/print-parity marker: {marker}")
for forbidden in (
    "Immutable snapshot.",
    "This preview is backed by",
    "Printed on the approved company headpad.",
    "Immutable final records",
):
    if forbidden in js:
        fail(f"production Documents UI reintroduced explanatory copy: {forbidden}")
if "return `${months[Math.max(0,Math.min(11,month-1))]} ${year}`;" in js:
    fail("document period label regressed to the out-of-scope months identifier")
if "<iframe" in js or "/print/?embed=1" in js:
    fail("Documents workspace must not embed the print route in an iframe")

print_template = text("templates/documents/print.html")
for marker in (
    "@page:first { size: A4; margin: 0; }",
    "thead { display:table-header-group; }",
    "break-inside:avoid; page-break-inside:avoid;",
    ".cover-sheet { height:297mm; overflow:hidden; break-after:page; page-break-after:always; }",
    ".continuation-sheet { padding:14mm 13mm 16mm; }",
    '<div class="cover-brand"><img src="{{ headpad_url }}" alt=""></div>',
    "continuation-title-row",
    "document.document_type == 'supplier_invoice'",
    "snapshot.invoice.total_in_words",
    "snapshot.payment.amount_in_words",
    "Project Timesheet · {{ document.document_number }}",
    "Supplier Timesheet Statement · {{ document.document_number }}",
    "Supplier Settlement Statement · {{ document.document_number }}",
    "Supplier Payment Advice · {{ document.document_number }}",
    "row.supplier_invoice_number",
):
    if marker not in print_template:
        fail(f"production print contract marker missing: {marker}")
for forbidden in (
    "position:fixed",
    "Printed on the approved company headpad.",
    "Immutable final snapshot",
    "This invoice is an immutable",
):
    if forbidden in print_template:
        fail(f"production print template reintroduced non-production/explanatory content: {forbidden}")

models = text("apps/documents/models.py")
for doc_type in contract["document_types"]:
    if f'"{doc_type}"' not in models:
        fail(f"document type missing from immutable model: {doc_type}")
for label in ("Supplier Settlement Statement", "Supplier Invoice Received", "Supplier Payment Advice"):
    if label not in models:
        fail(f"production document label missing: {label}")

rental_selector = text("apps/rental_manpower/selectors/settlements.py")
for marker in ("with_supplier_invoice_authority", '"payable": str(payable)', '"canRecordSupplierInvoice"'):
    if marker not in rental_selector:
        fail(f"supplier invoice payable authority missing: {marker}")
rental_service = text("apps/rental_manpower/services/settlements.py")
for marker in ("def _supplier_invoice_payable", "Record the supplier invoice before the first supplier payment.", "available = _money(payable - paid - processing)"):
    if marker not in rental_service:
        fail(f"supplier payment invoice authority missing: {marker}")
nginx = text("nginx/default.conf")
if 'add_header X-Frame-Options "DENY" always;' not in nginx:
    fail("global clickjacking protection must remain DENY")
if 'X-Frame-Options "SAMEORIGIN"' in nginx or 'proxy_hide_header X-Frame-Options;' in nginx:
    fail("document iframe exception must not be present")

print(
    "Verified Payroll document production contract: 7 immutable document types, "
    "canonical SESCCO A4 first-page headpad, plain continuation pages, native first-page preview with separate full print, "
    "supplier-specific Timesheet Statements, Supplier -> SESCCO invoice-received authority, batch supplier documents and invoice-gated payments."
)
