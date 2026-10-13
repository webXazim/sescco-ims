#!/usr/bin/env python3
"""Upgrade 07 static release-safety contract. Django tests still run in Docker."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def require(path, *needles):
    content = (ROOT / path).read_text()
    for needle in needles:
        assert needle in content, f"{path}: missing {needle}"
    if path.endswith(".py"):
        ast.parse(content, filename=path)


require("apps/sourcing/models/subcontractors.py", "class SourcingSubcontractorDocument", "on_delete=models.PROTECT", "def expired", "def effective_status")
require("apps/sourcing/migrations/0012_subcontractor_qualification_documents.py", "0011_subcontractor_company_verification", "SourcingSubcontractorDocument")
require("apps/sourcing/services/subcontractor_documents.py", "MAX_BYTES", "def inspect_upload", "default_storage.save(", "def review_document", "def delete_document", "transaction.on_commit", "_audit(")
require("apps/sourcing/views.py", "def subcontractor_document_create", "def subcontractor_document_edit", "def subcontractor_document_download", "def subcontractor_document_review", "def subcontractor_document_delete", "_require_subcontractor_manage(request)", "_require_subcontractor_view(request)", 'response["Cache-Control"] = "private, no-store, max-age=0"', 'response["X-Content-Type-Options"] = "nosniff"')
require("apps/sourcing/services/subcontractors.py", "Remove qualification documents before permanently deleting this subcontractor")
require("apps/sourcing/forms.py", "class SourcingSubcontractorDocumentForm", "inspect_upload")
require("templates/sourcing/subcontractors/_qualifications.html", "{% csrf_token %}", "qualifications", "qualification_page", "effective_status")
require("templates/sourcing/subcontractors/document_form.html", 'enctype="multipart/form-data"', "form.upload")
require("templates/sourcing/subcontractors/detail.html", 'include "sourcing/subcontractors/_qualifications.html"')
require("nginx/default.conf", "location /media/ {", "return 404;")
require("apps/sourcing/tests/test_subcontractor_qualifications.py", "test_tenant_isolation_and_independent_access", "test_invalid_upload_signature_and_date_range", "test_permanent_remove_cleans_file_and_parent_delete_is_protected")
assert "SourcingSubcontractorDocument" in (ROOT / "apps/sourcing/models/__init__.py").read_text()
assert "reference_document_protected_delete" in (ROOT / "merge/lifecycle-retention-contract.json").read_text()
print("PASS: Upgrade 07 protected qualification source contract (Django runtime not executed).")
