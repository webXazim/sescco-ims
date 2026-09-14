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
if contract.get("release") != "1.0.82":
    fail("document production contract is not frozen at 1.0.82")
if len(contract.get("document_types") or []) != 7:
    fail("all seven Payroll document types must remain covered")

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
    'SESCCO_SUPPLIER_INVOICE_LETTERHEAD = "apps/documents/assets/sescco-supplier-invoice-letterhead-v1.png"',
    'branding_profile = "sescco_supplier_invoice_v1"',
    'branding_mode = "letterhead"',
    'watermark = None  # The official headpad already carries the SESCCO watermark.',
    'snapshot["document_schema_version"] = "2.0"',
    'snapshot["invoice"]["total_in_words"] = money_to_words',
    'DocumentType.SUPPLIER_PAYMENT_RECEIPT',
):
    if marker not in service:
        fail(f"document service lost production marker: {marker}")

views = text("apps/documents/views.py")
for marker in ('descriptor.get("package_path")', 'apps" / "documents" / "assets', 'digest.hexdigest() != descriptor.get("sha256")'):
    if marker not in views:
        fail(f"historical packaged-brand asset guard missing: {marker}")

api = text("apps/documents/api.py")
for marker in (
    'limit = min(25, max(1, int(request.GET.get("limit", 25))))',
    'Choose a document type before searching source records.',
    'source_id=OuterRef("pk")',
    '.annotate(_finalized=Exists(existing))',
    'if len(query) >= 2:',
):
    if marker not in api:
        fail(f"bounded document source lookup marker missing: {marker}")

js = text("static/payroll/js/app.js")
for marker in (
    "function documentSourceTypesForWorkspace()",
    "function cancelDocumentSourceRequest()",
    "document-source-search",
    "limit:'25'",
    "Full Payroll masters are never loaded into this drawer.",
    "approved SESCCO A4 company headpad",
):
    if marker not in js:
        fail(f"document finalization UI lost bounded/letterhead marker: {marker}")

print_template = text("templates/documents/print.html")
for marker in (
    "@page letterhead { size: A4; margin: 39mm 15mm 25mm; }",
    "thead { display: table-header-group; }",
    "break-inside: avoid; page-break-inside: avoid;",
    ".paper--letterhead .brand-layer { position:fixed;",
    "document.document_type == 'supplier_invoice'",
    "snapshot.invoice.total_in_words",
    "snapshot.payment.amount_in_words",
    "Approved overtime snapshot",
    "Overtime snapshot",
):
    if marker not in print_template:
        fail(f"production print contract marker missing: {marker}")

models = text("apps/documents/models.py")
for doc_type in contract["document_types"]:
    if f'"{doc_type}"' not in models:
        fail(f"document type missing from immutable model: {doc_type}")

print(
    "Verified Payroll document production contract: 7 immutable document types, "
    "versioned SESCCO A4 supplier-invoice headpad, bounded 25-result source lookup, "
    "and production print/page-break safeguards."
)
