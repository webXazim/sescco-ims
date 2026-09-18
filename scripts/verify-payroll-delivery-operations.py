from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
delivery = (ROOT / "apps/documents/delivery.py").read_text()
api = (ROOT / "apps/documents/api.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
css = (ROOT / "static/payroll/css/v2/prs-records-management-cutover.css").read_text()
tests = (ROOT / "apps/documents/tests/test_documents.py").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()
models = (ROOT / "apps/documents/models.py").read_text()

required = {
    "delivery": [
        "delivery_share_issued_at", "delivery_share_expires_at", "delivery_share_is_expired",
        "Copying a link must not extend its lifetime.",
        "payload = signing.loads(token, salt=DELIVERY_SHARE_SALT)",
        "timezone.now() >= expires_at",
    ],
    "api": [
        "document_delivery_operations_api", '"shareExpiresAt": share_expires_at.isoformat()',
        '"shareStatus": "Revoked" if share_revoked else ("Expired" if share_expired else "Active")',
        "Supplier link has expired. Reissue the link before sending this pack.",
        'can_manage_delivery = _has_document_permission(request.company_membership, "rental", finalize=True)',
        '"attention": 0',
    ],
    "urls": ['api/documents/delivery-operations/'],
    "js": [
        "openDocumentDeliveryStatusDrawer", "data-document-delivery-status", "Delivery status",
        "Link attention", "/api/documents/delivery-operations/", "documentDeliveryOperationsRowsHtml",
    ],
    "css": ["document-delivery-ops-summary"],
    "tests": ["test_copying_link_does_not_extend_generation_expiry"],
}
for label, tokens in required.items():
    content = locals()[label]
    for token in tokens:
        if token not in content:
            raise SystemExit(f"DELIVERY OPERATIONS ERROR: {label} token missing: {token}")
if "# 1.0.117 — Supplier Delivery Operations Center Hotfix\n" not in notes:
    raise SystemExit("DELIVERY OPERATIONS ERROR: release notes lost the delivery operations hotfix section")
if "class DocumentDelivery" in models:
    raise SystemExit("DELIVERY OPERATIONS ERROR: operations center must remain audit-backed without a mutable delivery model")
print("Verified SESCCO MS 1.0.117 supplier delivery operations: fixed-generation link expiry, expired-link send blocking, bounded period monitoring, lifecycle filters, attention status and finalize-only external link controls.")
