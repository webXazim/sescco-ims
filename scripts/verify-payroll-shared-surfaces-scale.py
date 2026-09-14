#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL SHARED SURFACES SCALE ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


def require(rel: str, *needles: str) -> str:
    value = text(rel)
    for needle in needles:
        if needle not in value:
            fail(f"{rel} lost required contract text: {needle}")
    return value


if text("VERSION").strip() != "1.0.83":
    fail("VERSION must be 1.0.83")

contract = json.loads(text("merge/payroll-shared-surfaces-scale.json"))
if contract.get("release") != "1.0.83":
    fail("shared-surface contract release must be 1.0.83")
for key in ("documents", "reports", "record_management", "management", "browser"):
    if not isinstance(contract.get(key), dict):
        fail(f"missing {key} contract")
if contract.get("schema_change") is not False or contract.get("payroll_formula_change") is not False:
    fail("1.0.83 must not claim a schema or Payroll formula change")
for key in ("page_sizes",):
    if contract["documents"].get(key) != [25, 50, 100]:
        fail("document page sizes changed")
if contract["reports"].get("interactive_page_sizes") != [25, 50, 100]:
    fail("report page sizes changed")
if contract["record_management"].get("page_sizes") != [25, 50, 100]:
    fail("record-management page sizes changed")
if contract["management"].get("approval_preview_max") != 5:
    fail("management approval preview is no longer bounded to five")
if contract["management"].get("approval_page_sizes") != [25, 50, 100] or contract["management"].get("audit_page_sizes") != [25, 50, 100]:
    fail("management page sizes changed")

python_files = (
    "apps/documents/selectors/documents.py",
    "apps/documents/api.py",
    "apps/core/selectors/record_management.py",
    "apps/core/record_management_api.py",
    "apps/core/management/reports.py",
    "apps/core/management/selectors.py",
    "apps/core/management_api.py",
    "apps/core/payroll_views.py",
    "apps/core/api_urls.py",
)
for rel in python_files:
    try:
        ast.parse(text(rel))
    except SyntaxError as exc:
        fail(f"{rel} is not valid Python: {exc}")

require(
    "apps/documents/selectors/documents.py",
    "DOCUMENT_PAGE_SIZES = {25, 50, 100}",
    "def document_page_context(",
    '"deferred": True',
    "Paginator(",
)
require(
    "apps/documents/api.py",
    "document_page_context(",
    'request.GET.get("page", 1)',
    'request.GET.get("page_size", 50)',
    "include_snapshot=True",
)
require(
    "apps/core/selectors/record_management.py",
    "RECORD_PAGE_SIZES = {25, 50, 100}",
    "def record_management_page_context(",
    '"deferred": True',
)
require(
    "apps/core/record_management_api.py",
    "record_management_page_context(",
    'request.GET.get("q", "")',
)
require(
    "apps/core/management/reports.py",
    "REPORT_PAGE_SIZES = {25, 50, 100}",
    "def build_report_page(",
)
management_api = require(
    "apps/core/management_api.py",
    "build_report_page(",
    "build_report(",
    "def management_summary_api(",
    "def management_approvals_api(",
    "def management_audit_api(",
    "Capability.VIEW_AUDIT",
)
if management_api.index("build_report_page(") > management_api.index("def reports_api("):
    fail("interactive reports are no longer built through the paged report contract")
require(
    "apps/core/management/selectors.py",
    "MANAGEMENT_PAGE_SIZES = {25, 50, 100}",
    "def management_summary_context(",
    "def management_approval_page_context(",
    "def management_audit_page_context(",
    '"audit": []',
    '"deferredRecords": True',
)
require(
    "apps/core/payroll_views.py",
    "management_summary_context(",
)
require(
    "apps/core/api_urls.py",
    '"api/management/summary/"',
    '"api/management/approvals/"',
    '"api/management/audit/"',
    '"api/record-management/"',
)

js = require(
    "static/payroll/js/app.js",
    "/api/documents/?",
    "/api/reports/?",
    "/api/record-management/?",
    "/api/management/summary/?",
    "/api/management/approvals/?",
    "/api/management/audit/?",
    "cancelDocumentListRequest",
    "cancelReportRequest",
    "cancelRecordManagementRequest",
    "cancelManagementApprovalRequest",
    "cancelManagementAuditRequest",
)
for forbidden in (
    "state.businessDocuments.filter(",
    "state.managementAudit.filter(",
):
    if forbidden in js:
        fail(f"live Payroll UI regained a full-array filter: {forbidden}")

authority = json.loads(text("merge/payroll-data-authority.json"))
allow = set(authority.get("browser_storage_allowlist") or [])
for key in contract["browser"]["page_size_preferences"]:
    if key not in allow:
        fail(f"UI-only page-size preference is not allowlisted: {key}")

tests = {
    "apps/documents/tests/test_documents.py": [
        "test_document_directory_is_server_paginated_and_bootstrap_deferred",
    ],
    "apps/core/tests/test_management_reporting.py": [
        "test_interactive_report_contract_is_server_paginated",
        "test_management_shell_and_shared_record_registers_are_deferred_and_paginated",
    ],
    "apps/core/tests/test_merge_management_access.py": [
        "test_paginated_management_audit_api_keeps_company_boundary",
    ],
}
for rel, methods in tests.items():
    tree = ast.parse(text(rel))
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for method in methods:
        if method not in names:
            fail(f"missing regression evidence {rel}::{method}")

print("Verified Payroll shared surfaces scale: Documents, Reports, Record Management, Approval Center and Audit Trail are bounded and server-authoritative.")
