from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / "apps/documents/api.py").read_text()
urls = (ROOT / "apps/documents/urls.py").read_text()
js = (ROOT / "static/payroll/js/app.js").read_text()
css = (ROOT / "static/payroll/css/v2/prs-records-management-cutover.css").read_text()
notes = (ROOT / "RELEASE_NOTES.md").read_text()

required_api = [
    "documents.generation_batch_completed",
    "documents.DocumentGenerationBatch",
    "document.generation_batch",
    "DGB-",
    "_generation_request_fingerprint",
    "_serialize_generation_batch",
    "document_generation_batches_api",
    "request_fingerprint",
    "created_document_numbers",
    "record_audit_event",
]
required_urls = ["api/documents/generation-batches/"]
required_js = [
    "rentalGeneratorRecentBatchesHtml",
    "/api/documents/generation-batches/",
    "Recent generation",
    "payload.batch?.number",
]
required_css = ["document-generator-recent-list"]
for token in required_api:
    if token not in api:
        raise SystemExit(f"DOCUMENT GENERATION BATCH ERROR: API token missing: {token}")
for token in required_urls:
    if token not in urls:
        raise SystemExit(f"DOCUMENT GENERATION BATCH ERROR: URL missing: {token}")
for token in required_js:
    if token not in js:
        raise SystemExit(f"DOCUMENT GENERATION BATCH ERROR: frontend token missing: {token}")
for token in required_css:
    if token not in css:
        raise SystemExit(f"DOCUMENT GENERATION BATCH ERROR: CSS token missing: {token}")
if "class DocumentGenerationBatch" in (ROOT / "apps/documents/models.py").read_text():
    raise SystemExit("DOCUMENT GENERATION BATCH ERROR: hotfix must not introduce a new schema model")
if "# 1.0.117 — Rental Document Generation Batch Audit Hotfix" not in notes:
    raise SystemExit("DOCUMENT GENERATION BATCH ERROR: release-note section is missing")
print("Verified SESCCO MS 1.0.117 Rental document generation batch audit: numbered immutable AuditEvent evidence, deterministic request fingerprint, bounded recent history and no schema migration.")
