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
if not print_contract.get("preview_uses_print_route"):
    fail("document preview must use the same print route as production printing")
workflow = contract.get("supplier_invoice_workflow") or {}
for key in (
    "settlement_statement_generated_by_sescco", "supplier_invoice_received_record",
    "supplier_invoice_attachment_required", "supplier_invoice_attachment_hash_verified",
    "supplier_payment_requires_invoice_before_first_payment",
    "payment_payable_uses_invoice_total_including_vat", "supplier_payment_advice_generated_by_sescco",
    "batch_settlement_statements",
):
    if workflow.get(key) is not True:
        fail(f"supplier invoice workflow guarantee changed: {key}")
if workflow.get("direction") != "supplier_to_sescco" or workflow.get("sescco_generates_supplier_tax_invoice") is not False:
    fail("supplier invoice direction must remain Supplier -> SESCCO, not buyer-issued")
if workflow.get("schema_change") is not False:
    fail("supplier invoice-received hotfix must not add a database schema change")

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
for marker in (
    'SESCCO_COMPANY_DOCUMENT_HEADPAD = "apps/documents/assets/sescco-company-document-headpad-v2.png"',
    'SESCCO_SUPPLIER_INVOICE_LETTERHEAD = SESCCO_COMPANY_DOCUMENT_HEADPAD',
    'title = f"Supplier Invoice Received · {entity_name}"',
    'title = f"Supplier Settlement Statement · {entity_name}"',
    'title = f"Supplier Payment Advice · {entity_name}"',
    'branding_mode = "letterhead"',
    'snapshot["invoice"]["total_in_words"] = money_to_words',
    '"attachment": invoice.get("attachment")',
    '"supplier_invoice_number": (invoice_by_settlement.get',
    'snapshot["document_schema_version"] = "2.0"',
    'snapshot["invoice"]["total_in_words"] = money_to_words',
    'DocumentType.SUPPLIER_PAYMENT_RECEIPT',
):
    if marker not in service:
        fail(f"document service lost production marker: {marker}")

views = text("apps/documents/views.py")
for marker in ('descriptor.get("package_path")', 'apps" / "documents" / "assets', 'digest.hexdigest() != descriptor.get("sha256")', 'return static("payroll/assets/sescco-company-document-headpad-v2.png")', '@xframe_options_sameorigin', 'request.GET.get("embed") == "1"', 'def document_source_attachment', 'Supplier invoice attachment integrity verification failed.'):
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
):
    if marker not in api:
        fail(f"bounded document source lookup marker missing: {marker}")

js = text("static/payroll/js/app.js")
for marker in (
    "function documentSourceTypesForWorkspace()",
    "function cancelDocumentSourceRequest()",
    "function setupDocumentSourceCombobox()",
    "key:'document-source',endpoint:'/api/documents/sources/'",
    "function documentPrintPreview(doc)",
    "/print/?embed=1",
    "document-print-preview",
    "supplier_invoice:{label:'Supplier Invoice Received',code:'IR'}",
    "supplier_settlement:{label:'Supplier Settlement Statement',code:'SS'}",
    "supplier_payment_receipt:{label:'Supplier Payment Advice',code:'PA'}",
    'name="document-invoice-file"',
    "appMultipartApi('/api/documents/'",
    "data-document-batch-settlements",
    "function createSupplierSettlementStatementBatch()",
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
    "Rental Timesheet · {{ document.document_number }}",
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
if 'location ~ ^/documents/[0-9a-fA-F-]+/print/$' not in nginx or 'X-Frame-Options "SAMEORIGIN"' not in nginx:
    fail("same-origin document preview gateway exception is missing")

print(
    "Verified Payroll document production contract: 7 immutable document types, "
    "canonical SESCCO A4 first-page headpad, plain continuation pages, shared preview/print route, "
    "Supplier -> SESCCO invoice-received authority, batch settlement statements and invoice-gated payments."
)
