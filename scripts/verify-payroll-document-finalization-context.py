#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DOCUMENT CONTEXT ERROR: {message}")

def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

if text("VERSION").strip() != "1.0.111":
    fail("VERSION must be 1.0.111")
contract = json.loads(text("merge/payroll-document-finalization-context.json"))
if contract.get("release") != "1.0.111":
    fail("document finalization context contract release must be 1.0.111")

employee = contract.get("employee_salary_slip") or {}
for key in (
    "document_type_locked", "employee_locked", "period_locked", "backend_employee_scope",
    "auto_select_single_eligible_source", "approved_or_later_only", "stay_on_employee_documents_after_finalize",
):
    if employee.get(key) is not True:
        fail(f"employee salary-slip context guarantee changed: {key}")
if employee.get("global_employee_search") is not False:
    fail("employee profile salary-slip finalization must not expose company-wide employee search")

type_fields = contract.get("type_specific_fields") or {}
if type_fields.get("supplier_invoice_fields_created_only_for_supplier_invoice") is not True:
    fail("Supplier Invoice fields must be created only for Supplier Invoice")
for key in ("salary_slip_supplier_fields", "internal_timesheet_supplier_fields", "salary_payment_receipt_supplier_fields"):
    if type_fields.get(key) is not False:
        fail(f"supplier fields leaked into {key}")

api = text("apps/documents/api.py")
for marker in (
    'raw_employee_id = request.GET.get("employee_id", "").strip()',
    'scoped_employee_id = uuid.UUID(raw_employee_id)',
    'document_type not in {DocumentType.SALARY_SLIP, DocumentType.SALARY_PAYMENT_RECEIPT}',
    'and scoped_employee_id is None',
    'qs = qs.filter(employee_id=scoped_employee_id)',
    '"employeeScoped": scoped_employee_id is not None',
    'page_size = min(25',
    'stop = start + page_size + 1',
):
    if marker not in api:
        fail(f"backend employee-context source marker missing: {marker}")
block = api[api.index("def document_sources_api"):api.index("def document_detail_api")]
if "Paginator(" in block or ".count()" in block:
    fail("document source lookup must remain count-free")

js = text("static/payroll/js/app.js")
for marker in (
    "function renderDocumentTypeSpecificFields(type)",
    "host.innerHTML=type==='supplier_invoice'",
    "async function openDocumentGenerateDrawer(preferredType='', context={})",
    "const employeeScoped=Boolean(state.workspace==='internal'&&employee&&requestedType==='salary_slip')",
    "hideSearch:employeeScoped",
    "employee_id:scopedEmployeeId",
    "autoSelectSingle:Boolean(scopedEmployeeId)",
    "This drawer is locked to the selected employee and working period.",
    "stayOnEmployee",
    "Finalizing creates an immutable salary-slip snapshot; it does not recalculate Payroll.",
):
    if marker not in js:
        fail(f"frontend contextual-finalization marker missing: {marker}")
if '<section class="form-section" data-document-invoice-fields hidden>' in js:
    fail("Supplier Invoice fields are still pre-rendered into every document drawer")
if "openDocumentGenerateDrawer('Salary Slip',{ employeeId:currentEmployeeId(), period:state.period })" not in js:
    fail("Internal Employee Documents action no longer passes employee context")

css = text("static/payroll/css/v2/payroll-controls.css")
if '[data-document-invoice-fields][hidden]' not in css or 'display: none !important;' not in css:
    fail("defensive hidden Supplier Invoice section CSS guard is missing")

tests = text("apps/documents/tests/test_merge_access.py")
for method in (
    "test_employee_scoped_salary_slip_sources_do_not_require_global_search",
    "test_employee_scope_cannot_be_applied_to_non_employee_document_type",
):
    if f"def {method}" not in tests:
        fail(f"missing Django regression: {method}")

print("Verified SESCCO MS 1.0.111 contextual Payroll document finalization: employee-locked Salary Slip sources and type-only Supplier Invoice fields.")
