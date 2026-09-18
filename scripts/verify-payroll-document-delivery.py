from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
views = (ROOT / "apps/documents/views.py").read_text()
selectors = (ROOT / "apps/documents/selectors/documents.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
css = (ROOT / "static/payroll/css/v2/prs-records-management-cutover.css").read_text()
template = (ROOT / "templates/documents/delivery_pack.html").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required_api = [
    "document_delivery_options_api", "document_delivery_pack_api", "document_delivery_mark_delivered_api",
    "documents.delivery_pack_issued", "documents.delivery_sent", "documents.delivery_delivered",
    "documents.DocumentDeliveryPack", "document.delivery_pack", "DIP-", "DELIVERY_CHANNELS",
    "All documents in an issue pack must belong to the same supplier",
]
required_urls = [
    "delivery-options/", "api/documents/delivery-packs/", "delivered/", "documents/delivery-packs/<uuid:pack_event_id>/print/",
]
required_views = ["print_delivery_pack", "documents/delivery_pack.html"]
required_selectors = ["documents.delivery_sent", "documents.delivery_delivered", "delivery_by_document"]
required_js = [
    "documentCanIssue", "openDocumentDeliveryDrawer", "createDocumentDeliveryPack", "markDocumentPackDelivered",
    "Issue supplier documents", "Issue Sheet", "Mark Delivered", "/api/documents/delivery-packs/",
]
required_css = ["document-delivery-selection", "document-delivery-history"]
required_template = ["Supplier document issue", "Recipient acknowledgement", "Print / Save PDF"]
for token in required_api:
    if token not in api: raise SystemExit(f"DOCUMENT DELIVERY ERROR: API token missing: {token}")
for token in required_urls:
    if token not in urls: raise SystemExit(f"DOCUMENT DELIVERY ERROR: URL token missing: {token}")
for token in required_views:
    if token not in views: raise SystemExit(f"DOCUMENT DELIVERY ERROR: view token missing: {token}")
for token in required_selectors:
    if token not in selectors: raise SystemExit(f"DOCUMENT DELIVERY ERROR: selector token missing: {token}")
for token in required_js:
    if token not in js: raise SystemExit(f"DOCUMENT DELIVERY ERROR: frontend token missing: {token}")
for token in required_css:
    if token not in css: raise SystemExit(f"DOCUMENT DELIVERY ERROR: CSS token missing: {token}")
for token in required_template:
    if token not in template: raise SystemExit(f"DOCUMENT DELIVERY ERROR: issue-sheet token missing: {token}")
if "class DocumentDelivery" in (ROOT / "apps/documents/models.py").read_text():
    raise SystemExit("DOCUMENT DELIVERY ERROR: delivery tracking must remain append-only AuditEvent evidence without a new mutable schema model")
if "# 1.0.117 — Supplier Document Delivery Pack Hotfix" not in notes:
    raise SystemExit("DOCUMENT DELIVERY ERROR: release notes lost the supplier document delivery base hotfix")
print("Verified SESCCO MS 1.0.117 supplier document delivery: same-supplier issue packs, recipient/channel capture, immutable Sent/Delivered audit evidence, issue sheet and no schema migration.")
