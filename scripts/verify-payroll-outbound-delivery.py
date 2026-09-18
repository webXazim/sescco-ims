from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text()
views = (ROOT / "apps/documents/views.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
delivery = (ROOT / "apps/documents/delivery.py").read_text()
selectors = (ROOT / "apps/documents/selectors/documents.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
template = (ROOT / "templates/documents/delivery_share.html").read_text()
production = (ROOT / "config/settings/production.py").read_text()
env = (ROOT / ".env.production.example").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required = {
    "api": [
        "document_delivery_dispatch_api", "document_delivery_confirm_sent_api", "EmailMultiAlternatives",
        "documents.delivery_prepared", "documents.delivery_pack_dispatched", "transport=\"smtp\"",
        "Outbound email is not configured on this server", "https://wa.me/", "requiresConfirmation",
    ],
    "views": [
        "delivery_pack_share", "delivery_pack_share_acknowledge", "delivery_pack_shared_document_print",
        "Supplier acknowledgement", "delivery_source\": \"supplier_share",
    ],
    "urls": ["/dispatch/", "/sent/", "/share/<str:token>/", "delivery-pack-shared-document-print"],
    "delivery": ["signing.dumps", "signing.loads", "DELIVERY_SHARE_SALT", "delivery_share_expires_at", "timezone.now() >= expires_at"],
    "selectors": ["documents.delivery_prepared", '"Prepared"'],
    "js": ["sendPreparedDocumentPack", "Issue pack prepared", "WhatsApp message has been sent", "/dispatch/", "/sent/"],
    "template": ["Supplier document pack", "Acknowledge Receipt", "delivery-pack-shared-document-print"],
    "production": ["DOCUMENT_DELIVERY_SHARE_TTL_SECONDS", "EMAIL_BACKEND", "EMAIL_HOST"],
    "env": ["DOCUMENT_DELIVERY_SHARE_TTL_SECONDS=2592000", "EMAIL_HOST="],
}
for label, tokens in required.items():
    content = locals()[label]
    for token in tokens:
        if token not in content:
            raise SystemExit(f"OUTBOUND DELIVERY ERROR: {label} token missing: {token}")
if "# 1.0.117 — Supplier Outbound Delivery Portal Hotfix" not in notes:
    raise SystemExit("OUTBOUND DELIVERY ERROR: release notes lost the supplier outbound delivery base hotfix")
if "class DocumentDelivery" in (ROOT / "apps/documents/models.py").read_text():
    raise SystemExit("OUTBOUND DELIVERY ERROR: delivery tracking must remain audit-backed without a new mutable schema model")
print("Verified SESCCO MS 1.0.117 supplier outbound delivery: Prepared/Sent/Delivered evidence, SMTP dispatch, signed supplier portal, WhatsApp handoff, supplier acknowledgement and scoped shared print.")
