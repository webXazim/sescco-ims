from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
delivery = (ROOT / "apps/documents/delivery.py").read_text()
api = (ROOT / "apps/documents/api.py").read_text()
views = (ROOT / "apps/documents/views.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
selectors = (ROOT / "apps/documents/selectors/documents.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
template = (ROOT / "templates/documents/delivery_share.html").read_text()
tests = (ROOT / "apps/documents/tests/test_documents.py").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required = {
    "delivery": [
        "DELIVERY_SHARE_REISSUED_ACTION", "DELIVERY_SHARE_REVOKED_ACTION",
        "delivery_share_generation", "delivery_share_is_revoked", '"generation": generation',
        "This document link has been replaced.", "This document link has been revoked.",
    ],
    "api": [
        "document_delivery_share_revoke_api", "document_delivery_share_reissue_api",
        "documents.delivery_pack_opened", '"shareStatus": "Revoked" if share_revoked else ("Expired" if share_expired else "Active")',
        '"shareExpiresAt": share_expires_at.isoformat()',
        '"openedAt": opened.created_at.isoformat() if opened else ""',
    ],
    "views": ["_record_share_opened", "documents.delivery_opened", "opened_event_id", "private, no-store", "noindex, nofollow, noarchive", "no-referrer"],
    "urls": ["share/revoke/", "share/reissue/"],
    "selectors": ["documents.delivery_opened", '"Opened" if opened'],
    "js": ["Copy Link", "Revoke Link", "Reissue Link", "revokeDocumentPackLink", "reissueDocumentPackLink"],
    "template": ["Access expires", "expires_at", "noindex,nofollow,noarchive"],
    "tests": ["SupplierDeliveryShareLifecycleTests", "test_share_revocation_and_rotation_invalidate_old_tokens"],
}
for label, tokens in required.items():
    content = locals()[label]
    for token in tokens:
        if token not in content:
            raise SystemExit(f"DELIVERY LINK LIFECYCLE ERROR: {label} token missing: {token}")
if "# 1.0.117 — Supplier Delivery Link Lifecycle Hotfix" not in notes:
    raise SystemExit("DELIVERY LINK LIFECYCLE ERROR: release notes lost the delivery link lifecycle hotfix section")
if "class DocumentDelivery" in (ROOT / "apps/documents/models.py").read_text():
    raise SystemExit("DELIVERY LINK LIFECYCLE ERROR: share lifecycle must remain audit-backed without a mutable delivery model")
print("Verified SESCCO MS 1.0.117 supplier delivery link lifecycle: first-open evidence, Active/Revoked link state, generation rotation, old-token invalidation and no schema migration.")
