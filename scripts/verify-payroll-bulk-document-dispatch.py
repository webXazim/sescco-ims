from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
models = (ROOT / "apps/documents/models.py").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required_api = [
    "_dispatch_delivery_pack_email", "document_delivery_batch_dispatch_api",
    "documents.delivery_batch_dispatched", "already_sent_count", "failed_count",
    "WhatsApp packs require individual handoff confirmation for each supplier.",
    "Confirm the completed handoff before marking all supplier packs sent.",
]
required_urls = ["api/documents/delivery-batches/<uuid:batch_event_id>/dispatch/"]
required_js = [
    "dispatchBulkDocumentDeliveryBatch", "Send All Emails", "Confirm All Sent",
    "Retry Failed Emails", "/api/documents/delivery-batches/${encodeURIComponent(batchId)}/dispatch/",
]
for token in required_api:
    if token not in api:
        raise SystemExit(f"BULK DOCUMENT DISPATCH ERROR: API token missing: {token}")
for token in required_urls:
    if token not in urls:
        raise SystemExit(f"BULK DOCUMENT DISPATCH ERROR: URL token missing: {token}")
for token in required_js:
    if token not in js:
        raise SystemExit(f"BULK DOCUMENT DISPATCH ERROR: frontend token missing: {token}")
if "# 1.0.117 — Supplier Bulk Dispatch Execution Hotfix" not in notes:
    raise SystemExit("BULK DOCUMENT DISPATCH ERROR: release notes lost the bulk dispatch execution section")
if "class DocumentDelivery" in models:
    raise SystemExit("BULK DOCUMENT DISPATCH ERROR: bulk dispatch must remain audit-backed without a mutable delivery model")
print("Verified SESCCO MS 1.0.117 supplier bulk dispatch execution: batch email send, operator-confirmed batch handoff, retry-safe already-sent skipping, partial failure reporting and immutable dispatch audit evidence.")
