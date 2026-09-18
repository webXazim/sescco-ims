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

if text("VERSION").strip() != "1.0.117":
    fail("VERSION must be 1.0.117")
contract = json.loads(text("merge/payroll-document-finalization-context.json"))
if contract.get("release") != "1.0.117":
    fail("document finalization context contract release must be 1.0.117")

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
if type_fields.get("supplier_invoice_attachment_required") is not True:
    fail("Supplier Invoice Received must require the external supplier invoice attachment")
if type_fields.get("supplier_invoice_received_direction") != "supplier_to_sescco":
    fail("Supplier Invoice Received direction changed")
if type_fields.get("supplier_invoice_uses_multipart_upload") is not True:
    fail("Supplier Invoice Received must use multipart upload")
for key in ("salary_slip_supplier_fields", "internal_timesheet_supplier_fields", "salary_payment_receipt_supplier_fields"):
    if type_fields.get(key) is not False:
        fail(f"supplier fields leaked into {key}")

rental_docs = contract.get("rental_supplier_documents") or {}
for key in ("supplier_timesheet_statement", "supplier_timesheet_per_supplier_project", "batch_supplier_timesheets", "batch_settlement_statements", "supplier_invoice_received_from_settlement", "supplier_payment_advice_from_paid_payment"):
    if rental_docs.get(key) is not True:
        fail(f"rental supplier document guarantee changed: {key}")
if rental_docs.get("supplier_timesheet_source") != "locked_project_timesheet_supplier_scope":
    fail("Supplier Timesheet source authority changed")

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
    'Supplier invoice file is required.',
    'def batch_supplier_settlement_statements_api',
    'def batch_supplier_timesheet_statements_api',
    'SUPPLIER_TIMESHEET_ALIAS',
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
    "state.drawerContext={selectedSource:null,employeeScoped,employeeId:employeeScoped?employeeId:'',period,type:preferred}",
    "stayOnEmployee",
    "function documentCreateActionLabel(type, employeeScoped=false)",
    "drawerSave.textContent=documentCreateActionLabel",
    'name="document-invoice-file"',
    "appMultipartApi('/api/documents/'",
    "function createSupplierSettlementStatementBatch()",
    "function createSupplierTimesheetStatementBatch()",
    "supplier_timesheet:{label:'Supplier Timesheet Statement',code:'ST'}",
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

print("Verified SESCCO MS 1.0.117 contextual Payroll document creation: employee-locked Salary Slip, supplier-specific Timesheet Statements, Supplier Invoice Received capture, and batch supplier documents.")
