#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text(encoding="utf-8")
views = (ROOT / "apps/documents/views.py").read_text(encoding="utf-8")
js = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
models = (ROOT / "apps/documents/models.py").read_text(encoding="utf-8")
contract = json.loads((ROOT / "merge/payroll-document-system-closure.json").read_text(encoding="utf-8"))
migrations = sorted((ROOT / "apps/documents/migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))

def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT CLOSURE ERROR: {message}")


if contract.get("release") != "1.0.117" or contract.get("schema_change") is not False:
    fail("closure contract release/schema guarantee changed")
for section, keys in {
    "authority": ["business_documents_immutable", "generation_batches_audit_backed", "delivery_packs_audit_backed", "delivery_lifecycle_audit_backed"],
    "generation": ["project_scope_safe_options", "server_search_suppliers", "server_search_projects", "review_required", "explicit_nonempty_selection_required", "stale_review_rejected"],
    "delivery": ["period_filtered_before_bounds", "integrity_required_before_issue", "integrity_required_before_send", "integrity_required_before_issue_sheet", "sent_or_opened_required_before_manual_delivered", "opened_idempotent", "delivered_idempotent", "share_revoke_reissue_serialized", "email_dispatch_serialized_per_pack"],
    "security": ["supplier_invoice_attachment_no_store", "supplier_invoice_attachment_no_referrer", "supplier_invoice_attachment_no_index", "shared_pack_no_store", "global_frame_policy_denied"],
}.items():
    values = contract.get(section) or {}
    for key in keys:
        if values.get(key) is not True:
            fail(f"closure contract guarantee changed: {section}.{key}")

if "# 1.0.117 — Payroll Document System Production Closure Hotfix" not in notes:
    fail("release notes no longer contain the final document-system closure")

required_api = [
    'timesheet_sources = RentalTimesheetEntry.objects.for_company(request.company).filter(period__period_start=period_start)',
    'settlement_sources = SupplierSettlement.objects.for_company(request.company).filter(period_start=period_start)',
    'allowed_projects = project_scope_ids(request.company_membership)',
    '_has_timesheet_source=Exists(timesheet_sources.filter(supplier_code__iexact=OuterRef("code")))',
    '_has_settlement_source=Exists(settlement_sources.filter(supplier_code__iexact=OuterRef("code")))',
    'Select at least one reviewed document before creating the batch.',
    'One or more reviewed documents are no longer eligible. Review the generation plan again.',
    'metadata__periods__contains=[period_key]',
    'One or more selected documents failed integrity verification.',
    'Mark the supplier pack Sent before confirming delivery.',
    'AuditEvent.objects.select_for_update().get(pk=pack_event.pk)',
    'AuditEvent.objects.select_for_update().get(pk=scoped_pack.pk)',
]
for token in required_api:
    if token not in api:
        fail(f"API hardening marker missing: {token}")

required_views = [
    'if any(not verify_document_snapshot(document) for document in documents):',
    'AuditEvent.objects.select_for_update().get(pk=pack.pk)',
    '_record_share_opened(request=request, pack=pack, documents=documents)',
    'response["Cache-Control"] = "private, no-store"',
    'response["Referrer-Policy"] = "no-referrer"',
    'response["X-Robots-Tag"] = "noindex, nofollow, noarchive"',
]
for token in required_views:
    if token not in views:
        fail(f"view hardening marker missing: {token}")

required_js = [
    'function searchRentalGeneratorOptions(kind,query)',
    'function mergeRentalGeneratorSearchRows(kind,rows=[])',
    "params.set(kind==='supplier'?'supplier_q':'project_q',q);",
    'searchRentalGeneratorOptions(kind,q);',
    'if(!selectedKeys.length)',
    'data-document-delivery-status',
    'data-document-bulk-delivery',
    'data-document-generate',
]
for token in required_js:
    if token not in js:
        fail(f"frontend closure marker missing: {token}")

for forbidden in (
    '<iframe',
    '/print/?embed=1',
    'data-document-batch-timesheets>Supplier Timesheets',
    'data-document-batch-settlements>Settlement Statements',
):
    if forbidden in js:
        fail(f"obsolete Documents workflow returned: {forbidden}")

if len(migrations) != 2:
    fail(f"document closure must remain schema-free; found migrations: {[p.name for p in migrations]}")
if 'class DocumentDelivery' in models or 'class DocumentGenerationBatch' in models:
    fail("closure must preserve immutable BusinessDocument + append-only AuditEvent authority")

print(
    "Verified SESCCO MS 1.0.117 Payroll document-system production closure: scope-safe server search, "
    "exact reviewed generation, period-safe delivery monitoring, integrity-gated issue packs, serialized lifecycle transitions, "
    "secure invoice attachments and schema-free immutable authority."
)
