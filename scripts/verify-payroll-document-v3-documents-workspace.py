#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/payroll/css/v2/pages/payroll.css").read_text(encoding="utf-8")
SELECTOR = (ROOT / "apps/documents/selectors/documents.py").read_text(encoding="utf-8")
API = (ROOT / "apps/documents/api.py").read_text(encoding="utf-8")
TESTS = (ROOT / "apps/documents/tests/test_v3_documents_workspace_cleanup.py").read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT V3 DOCUMENTS WORKSPACE ERROR: {message}")


def require(source: str, needle: str, message: str) -> None:
    if needle not in source:
        fail(message)


require(JS, "const rentalFamilies=[", "Rental business-family catalog is missing")
family_start = JS.index("const rentalFamilies=[")
family_end = JS.index("const internalFamilies=[", family_start)
families = JS[family_start:family_end]
for key in ("supplier_timesheet", "supplier_settlement", "supplier_invoice", "supplier_payment_receipt"):
    require(families, key, f"Rental Documents workspace lost business family {key}")
if "rental_timesheet" in families:
    fail("Project Timesheet must stay secondary and must not return as a primary Rental Documents family")

for needle, message in (
    ("All records", "All-records history tab is missing"),
    ("Open Project Timesheets", "operational Project Timesheets handoff is missing"),
    ("data-document-project-timesheets", "Project Timesheets workspace action is missing"),
    ("documents-page--clean", "clean Documents workspace layout class is missing"),
    ("document-toolbar--clean", "clean Documents toolbar is missing"),
    ("document-workspace-note", "workspace guidance note is missing"),
    ("?view=summary", "selected-document preview still requests the full immutable snapshot"),
    ("full.preview||full.snapshot", "preview compatibility bridge is missing"),
    ("Preview stays lightweight", "lightweight preview disclosure is missing"),
):
    require(JS, needle, message)

template_start = JS.index("function documentsTemplate()")
template_end = JS.index("function documentSourceTypesForWorkspace", template_start)
template = JS[template_start:template_end]
if "documentStatusFilter" in template:
    fail("final-record workspace reintroduced the redundant status filter")

for needle, message in (
    ('Paginator(filtered.defer("snapshot"), size)', "register pagination no longer defers the large snapshot"),
    ("verify_integrity=False", "register serialization no longer defers per-row integrity hashing"),
    ("def document_preview_fragment", "bounded preview fragment selector is missing"),
):
    require(SELECTOR, needle, message)

preview_start = SELECTOR.index("def document_preview_fragment")
preview_end = SELECTOR.index("def document_page_context", preview_start)
preview_selector = SELECTOR[preview_start:preview_end]
for forbidden in ('"snapshot__workers"', '"snapshot__entries"', '"snapshot__allocations"'):
    if forbidden in preview_selector:
        fail(f"summary preview reintroduced a large snapshot collection: {forbidden}")

for needle, message in (
    ('summary_only = request.GET.get("view", "").strip().lower() == "summary"', "summary-detail mode is missing"),
    ('row_qs.defer("snapshot") if summary_only', "summary-detail query no longer defers the full snapshot"),
    ('previewMode"] = "summary"', "summary preview response marker is missing"),
):
    require(API, needle, message)

for hook in (
    "document-workspace-note",
    "document-toolbar--clean",
    "documents-page--clean",
    "document-native-preview__note",
):
    require(CSS, hook, f"missing Documents workspace layout hook: {hook}")

required_tests = (
    "test_register_page_defers_snapshot_integrity_and_uses_supplier_timesheet_family_count",
    "test_summary_detail_returns_small_preview_without_worker_array",
    "test_full_detail_remains_backward_compatible_and_integrity_verified",
    "test_rental_workspace_has_four_business_families_and_project_timesheet_stays_secondary",
    "test_documents_toolbar_removes_redundant_final_status_filter",
    "test_browser_requests_summary_preview_instead_of_full_snapshot",
    "test_backend_register_and_summary_paths_explicitly_defer_large_snapshot",
    "test_workspace_cleanup_has_dedicated_responsive_layout",
)
for method in required_tests:
    require(TESTS, f"def {method}", f"regression evidence missing: {method}")

print("Verified Supplier Timesheet Pack v3 Documents workspace cleanup and lightweight preview path.")
