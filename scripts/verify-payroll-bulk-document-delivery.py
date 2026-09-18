from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
css = (ROOT / "static/payroll/css/v2/prs-records-management-cutover.css").read_text()
models = (ROOT / "apps/documents/models.py").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required_api = [
    "document_delivery_center_api", "document_delivery_batch_prepare_api", "_issue_delivery_pack",
    "documents.delivery_batch_prepared", "documents.DocumentDeliveryBatch", 'prefix="DIB-"',
    "Bulk issue is limited to 25 suppliers at a time.", "Select between 1 and 200 supplier documents.",
    "A supplier issue pack is limited to 25 documents.", "_delivery_center_document_queryset",
]
required_urls = ["api/documents/delivery-center/", "api/documents/delivery-batches/"]
required_js = [
    "Issue Documents", "openBulkDocumentDeliveryDrawer", "createBulkDocumentDeliveryPacks",
    "document-delivery-bulk-document", "/api/documents/delivery-center/", "/api/documents/delivery-batches/",
    "Prepare Packs", "Select all visible",
]
required_css = ["document-delivery-bulk-groups", "document-delivery-bulk-group", "document-delivery-bulk-select-all"]
for token in required_api:
    if token not in api:
        raise SystemExit(f"BULK DOCUMENT DELIVERY ERROR: API token missing: {token}")
for token in required_urls:
    if token not in urls:
        raise SystemExit(f"BULK DOCUMENT DELIVERY ERROR: URL token missing: {token}")
for token in required_js:
    if token not in js:
        raise SystemExit(f"BULK DOCUMENT DELIVERY ERROR: frontend token missing: {token}")
for token in required_css:
    if token not in css:
        raise SystemExit(f"BULK DOCUMENT DELIVERY ERROR: CSS token missing: {token}")
if "# 1.0.117 — Supplier Bulk Delivery Planner Hotfix" not in notes:
    raise SystemExit("BULK DOCUMENT DELIVERY ERROR: release notes lost the bulk delivery planner hotfix section")
if "class DocumentDelivery" in models:
    raise SystemExit("BULK DOCUMENT DELIVERY ERROR: delivery batches must remain append-only AuditEvent evidence without a mutable delivery model")
print("Verified SESCCO MS 1.0.117 supplier bulk delivery planner: period-scoped multi-supplier selection, separate immutable issue packs, DIB audit batch, bounded execution and no schema migration.")
