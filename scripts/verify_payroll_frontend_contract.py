#!/usr/bin/env python3
"""Static contract check between the frozen Payroll browser client and merged Django URLs."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
URL_FILES = [
    ROOT / "apps/internal_payroll/urls.py",
    ROOT / "apps/rental_manpower/urls.py",
    ROOT / "apps/documents/urls.py",
    ROOT / "apps/core/api_urls.py",
]


def django_routes() -> list[tuple[str, re.Pattern[str]]]:
    routes: list[tuple[str, re.Pattern[str]]] = []
    for file in URL_FILES:
        text = file.read_text(encoding="utf-8")
        for match in re.finditer(r"path\(\s*[\"']([^\"']+)[\"']", text):
            raw = "/" + match.group(1)
            parts = re.split(r"(<[^>]+>)", raw)
            regex = "".join(r"[^/]+" if part.startswith("<") else re.escape(part) for part in parts)
            routes.append((raw, re.compile(r"^" + regex + r"$")))
    return routes


def frontend_urls() -> list[str]:
    urls: set[str] = set()
    patterns = (
        r"'(/(?:api|documents)/[^']*)'",
        r'"(/(?:api|documents)/[^"]*)"',
        r"`(/(?:api|documents)/[^`]*)`",
    )
    for pattern in patterns:
        for body in re.findall(pattern, JS):
            body = body.split("?", 1)[0]
            body = re.sub(r"\$\{[^}]+\}", "__id__", body)
            urls.add(body)
    return sorted(urls)


routes = django_routes()
client_urls = frontend_urls()
missing = [url for url in client_urls if not any(pattern.fullmatch(url) for _, pattern in routes)]

if missing:
    print("Payroll frontend URLs without a merged Django route:")
    for url in missing:
        print(f"  - {url}")
    raise SystemExit(1)

required_prefixes = {
    "/api/internal/",
    "/api/rental/",
    "/api/documents/",
    "/api/management/",
    "/api/reports/",
    "/api/settings/",
    "/documents/",
}
seen = {prefix for prefix in required_prefixes if any(url.startswith(prefix) for url in client_urls)}
missing_prefixes = sorted(required_prefixes - seen)
if missing_prefixes:
    raise SystemExit(f"Payroll client no longer references expected API domains: {missing_prefixes}")

print(f"Verified {len(client_urls)} Payroll browser URL contracts against {len(routes)} Django routes.")

# Production search/filter/sort contract. Search fields that redraw Payroll route content must
# use the shared debounced binding so large registers do not rerender on every keystroke.
search_ids = {
    "managementAuditSearch", "branchSearch", "departmentSearch", "employeeSearch",
    "projectSearch", "projectWorkerSearch", "supplierSearch", "supplierWorkerSearch",
    "salaryComponentSearch", "salaryStructureSearch", "timesheetSearch", "rentalTimesheetSearch",
    "payrollSearch", "wpsSearch", "bankExportSearch", "paymentSearch", "rentalAssignmentSearch",
    "rentalSearch", "rentalSettlementSearch", "adjustmentSearch", "documentSearch", "reportSearch",
}
for search_id in sorted(search_ids):
    if f"getElementById('{search_id}')" not in JS:
        raise SystemExit(f"Payroll search input is not wired by id: {search_id}")

required_ui_contracts = {
    "shared debounced search": "function bindPayrollSearch(input, setter",
    "persistent table sorting": "const payrollTableSortPrefs",
    "sortable table enhancer": "function enhancePayrollSortableTables(root = pageRoot)",
    "route sorting activation": "enhancePayrollSortableTables(pageRoot);",
    "project advanced filters": "id=\"projectClientFilter\"",
    "supplier advanced filters": "id=\"supplierProjectFilter\"",
    "project workforce filters": "id=\"projectWorkerSupplierFilter\"",
    "supplier workforce filters": "id=\"supplierWorkerProjectFilter\"",
    "branch explicit sorting": "id=\"branchSortFilter\"",
    "department explicit sorting": "id=\"departmentSortFilter\"",
    "readonly payroll detail drawer": "configureDrawerPresentation({ eyebrow:'Payroll run', ariaLabel:'Payroll calculation details', footerVisible:false })",
    "numeric payroll detail deductions": "const totalDeductions = advances + otherDeductions;",
    "payroll detail register reconciliation": "Same saved row used by Payroll Register",
}
for label, marker in required_ui_contracts.items():
    if marker not in JS:
        raise SystemExit(f"Payroll production register contract missing {label}: {marker}")

for forbidden in (
    "filters are reserved for production data",
    "filters are planned for this supplier worker view",
):
    if forbidden in JS.lower():
        raise SystemExit(f"Payroll still contains a non-functional filter placeholder: {forbidden}")

query_controls = (ROOT / "apps/core/query_controls.py").read_text(encoding="utf-8")
for marker in ("allowed_sorts", "max_page_size", "Paginator", "Stable tie-breakers"):
    if marker not in query_controls:
        raise SystemExit(f"Payroll API list-control contract missing: {marker}")

for api_file in (ROOT / "apps/internal_payroll/api.py", ROOT / "apps/rental_manpower/api.py"):
    api_text = api_file.read_text(encoding="utf-8")
    for marker in ("parse_list_controls", "apply_ordering", "serialize_list"):
        if marker not in api_text:
            raise SystemExit(f"{api_file.name} is missing production list control {marker}")

print("Verified Payroll production search/filter/sort contracts.")

# Attendance/status authority contract. Internal and Rental input, imports and workflow
# transitions must share the backend vocabulary; browser aliases are never the source of truth.
attendance_contract = (ROOT / "apps/core/payroll_attendance_contract.py").read_text(encoding="utf-8")
internal_attendance_service = (ROOT / "apps/internal_payroll/services/attendance.py").read_text(encoding="utf-8")
rental_timesheet_service = (ROOT / "apps/rental_manpower/services/timesheets.py").read_text(encoding="utf-8")
internal_attendance_selector = (ROOT / "apps/internal_payroll/selectors/attendance.py").read_text(encoding="utf-8")
rental_timesheet_selector = (ROOT / "apps/rental_manpower/selectors/timesheets.py").read_text(encoding="utf-8")
rental_master_selector = (ROOT / "apps/rental_manpower/selectors/masters.py").read_text(encoding="utf-8")
for label, marker in {
    "Internal status contract": '("H", "Holiday", "holiday")',
    "Rental status contract": '("N", "No Scope", "noscope")',
    "blank/missing authority": '"blankMeansMissing": True',
    "explicit-code completeness": '"explicitStatusCompletesDay": True',
    "workflow aliases": '"submit_for_review": "submit"',
    "reject/return alias": '"reject": "return_to_draft"',
    "backend normalizer": "def normalize_payroll_attendance_value(",
}.items():
    if marker not in attendance_contract:
        raise SystemExit(f"Payroll attendance authority contract missing {label}: {marker}")

for source, label in (
    (internal_attendance_service, "Internal attendance"),
    (rental_timesheet_service, "Rental timesheet"),
):
    for marker in ("normalize_payroll_attendance_value(", "normalize_attendance_workflow_action(action)"):
        if marker not in source:
            raise SystemExit(f"{label} does not use the shared backend attendance contract: {marker}")

for source, label in (
    (internal_attendance_selector, "Internal attendance API context"),
    (rental_timesheet_selector, "Rental timesheet API context"),
    (rental_master_selector, "Rental bootstrap context"),
):
    if '"attendanceContract": attendance_contract_payload(' not in source and "'attendanceContract': attendance_contract_payload(" not in source:
        raise SystemExit(f"{label} does not publish the backend attendance contract")

for marker in (
    "function normalizeAttendanceByContract(value, contract)",
    "state.internalAttendanceContract",
    "state.rentalAttendanceContract",
    "attendanceLegendItems(state.internalAttendanceContract)",
    "attendanceLegendItems(state.rentalAttendanceContract)",
    "action:'return_to_draft'",
    "const actionName=action.action",
):
    if marker not in JS:
        raise SystemExit(f"Payroll browser attendance-contract wiring missing: {marker}")

for forbidden in (
    "const aliases = { P: '8', PRESENT: '8', ABSENT: 'A'",
    "const aliases = { ABSENT:'A', SICK:'A'",
    ">Sick absent</button>",
    "else if (String(value) === '0') absent += 1;",
):
    if forbidden in JS:
        raise SystemExit(f"Browser attendance vocabulary has become authoritative again: {forbidden}")

zero_complete_marker = "else if (Number.isFinite(Number(raw)) && Number(raw) === 0) zero += 1;"
if JS.count(zero_complete_marker) < 2:
    raise SystemExit("Internal and Rental summaries must treat explicit zero hours as complete rather than missing/absent")
if JS.count("if (!raw) missing += 1;") < 2:
    raise SystemExit("Internal and Rental summaries must reserve missing status for genuinely blank entries")

print("Verified Internal/Rental attendance and workflow authority contracts.")

# Rental financial-authority contract. Project/supplier cost surfaces must be driven by
# immutable settlement snapshots and payment allocations, never bootstrap zero placeholders.
rental_settlements_selector = (ROOT / "apps/rental_manpower/selectors/settlements.py").read_text(encoding="utf-8")
rental_masters_selector = (ROOT / "apps/rental_manpower/selectors/masters.py").read_text(encoding="utf-8")
rental_authority_markers = {
    "settlement financial roll-up": "def rental_financial_metrics_from_settlements",
    "period financial roll-up": "def rental_financial_metrics_for_period",
    "settlement context financial metrics": '"financialMetrics": financial_metrics',
    "payable status boundary": "PAYABLE_SETTLEMENT_STATUSES",
    "serialized payable total": '"payable": str(payable)',
}
for label, marker in rental_authority_markers.items():
    if marker not in rental_settlements_selector:
        raise SystemExit(f"Rental financial authority contract missing {label}: {marker}")

for marker in (
    '"financialMetrics": financial_metrics',
    'serialize_supplier(item, supplier_metrics.get(str(item.pk)))',
    'serialize_project(item, project_metrics.get(project_public_id(item)))',
):
    if marker not in rental_masters_selector:
        raise SystemExit(f"Rental master bootstrap is not using settlement financial authority: {marker}")

for forbidden in (
    '"hours": 0', '"otHours": 0', '"currentCost": 0', '"outstanding": 0',
    '"grossCost": 0', '"advances": 0', '"netCost": 0',
):
    if forbidden in rental_masters_selector:
        raise SystemExit(f"Rental master financial placeholder returned to production selector: {forbidden}")

for marker in (
    "rentalFinancialMetricsByPeriod",
    "function rentalProjectFinancial(projectId, period = state.period)",
    "function rentalSupplierFinancial(supplierId, period = state.period)",
    "function rentalScopeFinancial(projectId, supplierId, period = state.period)",
    "state.rentalFinancialMetricsByPeriod[label] = payload.financialMetrics",
):
    if marker not in JS:
        raise SystemExit(f"Rental browser financial authority wiring missing: {marker}")

print("Verified Rental project/supplier financial authority contracts.")

# Internal employee-profile authority contract. Employee profile overtime, payroll history and
# activity must come from server records rather than zero/empty browser placeholders.
employee_profile_selector = (ROOT / "apps/internal_payroll/selectors/employee_profile.py").read_text(encoding="utf-8")
internal_api = (ROOT / "apps/internal_payroll/api.py").read_text(encoding="utf-8")
internal_urls = (ROOT / "apps/internal_payroll/urls.py").read_text(encoding="utf-8")
for label, marker in {
    "attendance/overtime selector": "AttendanceOvertimeEntry.objects.for_company(company)",
    "immutable payroll line history": "PayrollRunLine.objects.for_company(company)",
    "payment status history": 'Prefetch("payment_rows"',
    "audit activity": "AuditEvent.objects.filter(company=company, area=AuditArea.INTERNAL)",
    "profile context": "def employee_profile_context",
}.items():
    if marker not in employee_profile_selector:
        raise SystemExit(f"Employee profile authority contract missing {label}: {marker}")

for marker in (
    "def employee_profile_api",
    "employee_profile_context(",
    'path("api/internal/employees/<uuid:employee_id>/profile/"',
):
    source = internal_urls if marker.startswith('path(') else internal_api
    if marker not in source:
        raise SystemExit(f"Employee profile API contract missing: {marker}")

for marker in (
    "employeeProfileContexts",
    "function loadEmployeeProfileContext",
    "/api/internal/employees/${encodeURIComponent(employeeId)}/profile/",
    "serverProfile?.payrollHistory || []",
    "serverProfile?.activity || []",
    "otHours: Number(serverAttendance.otHours || 0)",
    "invalidateEmployeeProfile(employeeId)",
):
    if marker not in JS:
        raise SystemExit(f"Employee profile browser authority wiring missing: {marker}")

for forbidden in (
    "payrollHistory: [],",
    "activity: []",
    "regularHours: timesheetSummary.regularHours, otHours: 0",
):
    if forbidden in JS:
        raise SystemExit(f"Employee profile browser placeholder returned: {forbidden}")

print("Verified Internal employee profile backend-authority contracts.")

# Payroll directory authority contract. Register rows must come from paginated server APIs,
# while large employee organization histories are loaded only with the selected profile.
payroll_view = (ROOT / "apps/core/payroll_views.py").read_text(encoding="utf-8")
rental_api = (ROOT / "apps/rental_manpower/api.py").read_text(encoding="utf-8")
organization_selector = (ROOT / "apps/internal_payroll/selectors/organization.py").read_text(encoding="utf-8")
rental_master_selector = (ROOT / "apps/rental_manpower/selectors/masters.py").read_text(encoding="utf-8")
for marker in (
    "serverDirectories:",
    "function serverDirectoryRequest(kind)",
    "function loadServerDirectory(kind,{force=false}={})",
    "function serverDirectoryView(kind)",
    "function directoryPagination(kind,meta={})",
    "data-directory-page=",
    "data-directory-page-size=",
    "serverDirectoryView('branches')",
    "serverDirectoryView('departments')",
    "serverDirectoryView('employees')",
    "serverDirectoryView('projects')",
    "serverDirectoryView('suppliers')",
    "serverDirectoryView('workers')",
    "endpoint='/api/internal/branches/'",
    "endpoint='/api/internal/departments/'",
    "endpoint='/api/internal/employees/'",
    "endpoint='/api/rental/projects/'",
    "endpoint='/api/rental/suppliers/'",
    "endpoint='/api/rental/workers/'",
):
    if marker not in JS:
        raise SystemExit(f"Payroll server-directory browser contract missing: {marker}")

for marker in (
    'internal_master_context(company=request.company, include_histories=False, employee_limit=50, membership=membership)',
):
    if marker not in payroll_view:
        raise SystemExit(f"Payroll shell lost the bounded 50-row employee bootstrap contract: {marker}")

for marker in (
    '"organizationHistory": [',
):
    if marker not in employee_profile_selector:
        raise SystemExit(f"Employee organization history is not available on-demand from the profile API: {marker}")

for marker in (
    '"employees": "active_employee_count"',
    '"paymentProfile"] = profile',
    'result["wps"] = readiness_by_employee[employee_id]',
    'result["salaryConfigured"] = employee_id in salary_configured_ids',
):
    if marker not in internal_api:
        raise SystemExit(f"Internal server-directory contract missing: {marker}")

for marker in (
    'project_id = request.GET.get("project_id") or None',
    'payment_terms_raw = request.GET.get("payment_terms")',
    'outstanding_filter = str(request.GET.get("outstanding", "")).strip().lower()',
    'client_raw = request.GET.get("client")',
    'manager_raw = request.GET.get("manager")',
    'view_status = str(request.GET.get("view_status", "")).strip().lower().replace(" ", "_")',
    'rate_type = str(request.GET.get("rate_type", "")).strip().lower()',
):
    if marker not in rental_api:
        raise SystemExit(f"Rental server-directory API contract missing: {marker}")

for marker in (
    'active_employee_count=Count(',
    'employee_count=Count(',
):
    if marker not in organization_selector:
        raise SystemExit(f"Organization directory count contract missing: {marker}")

for marker in (
    '_has_current_assignment=Exists(current_assignments)',
    '_display_trade=Coalesce(',
    '_display_rate_type=Coalesce(',
):
    if marker not in rental_master_selector:
        raise SystemExit(f"Rental worker directory filter contract missing: {marker}")

for marker in (
    "function getFilteredEmployees() {\n    return serverDirectoryView('employees').rows;\n  }",
    "function getFilteredProjects() {\n    return serverDirectoryView('projects').rows;\n  }",
    "function rentalWorkforceRows() {\n    return serverDirectoryView('workers').rows;\n  }",
    "const directory = serverDirectoryView('branches');",
    "const directory = serverDirectoryView('departments');",
    "const directory = serverDirectoryView('suppliers');",
):
    if marker not in JS:
        raise SystemExit(f"Payroll directory is not server-authoritative: {marker}")

print("Verified Payroll server-side directory authority contracts.")

# Internal Payroll lifecycle authority contract (1.0.55). Browser actions must be
# published by backend selectors and every authoritative state transition must be revisioned.
payroll_service = (ROOT / "apps/internal_payroll/services/payroll.py").read_text(encoding="utf-8")
payment_service = (ROOT / "apps/internal_payroll/services/payment.py").read_text(encoding="utf-8")
payroll_selector = (ROOT / "apps/internal_payroll/selectors/payroll.py").read_text(encoding="utf-8")
payment_selector = (ROOT / "apps/internal_payroll/selectors/payment.py").read_text(encoding="utf-8")
payment_api = (ROOT / "apps/internal_payroll/payment_api.py").read_text(encoding="utf-8")
payroll_tests = (ROOT / "apps/internal_payroll/tests/test_payroll.py").read_text(encoding="utf-8")
payment_tests = (ROOT / "apps/internal_payroll/tests/test_payment.py").read_text(encoding="utf-8")

for marker in (
    '"submit_for_review": "submit_review"',
    '"reject": "return_for_changes"',
    'run.revision += 1',
):
    if marker not in payroll_service:
        raise SystemExit(f"Internal payroll lifecycle service contract missing: {marker}")

for marker in (
    '"workflow": {',
    '"allowedActions": allowed_actions',
    '"canCalculate": "calculate" in allowed_actions',
    '"canSubmitReview": "submit_review" in allowed_actions',
    '"canReview": "review" in allowed_actions',
    '"reviewSignedOff": review_signed_off',
    '"canReturnForChanges": "return_for_changes" in allowed_actions',
    '"canApprove": "approve" in allowed_actions',
):
    if marker not in payroll_selector:
        raise SystemExit(f"Internal payroll workflow selector contract missing: {marker}")

for marker in (
    'if can_pay and batch.status in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:',
    'allowed_actions.append("start")',
    'if can_prepare and batch.status in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:',
    'allowed_actions.append("cancel")',
    'if can_export and batch.status not in {SalaryPaymentBatchStatus.CANCELLED, SalaryPaymentBatchStatus.CLOSED}:',
    'allowed_actions.append("import_results")',
    'allowed_actions.append("close")',
    'allowed_actions.append("reopen")',
    '"canRetry": bool(can_pay',
):
    if marker not in payment_selector:
        raise SystemExit(f"Salary payment action authority contract missing: {marker}")

for marker in (
    '"start_processing": "start"',
    '"cancel_batch": "cancel"',
    '"close_payroll": "close"',
    '"reopen_payroll": "reopen"',
):
    if marker not in payment_api:
        raise SystemExit(f"Salary payment workflow API alias contract missing: {marker}")

for marker in (
    'run.revision += 1',
    'def start_salary_payment_batch(',
    'def close_salary_payment_batch(',
    'def reopen_salary_payment_batch(',
):
    if marker not in payment_service:
        raise SystemExit(f"Salary payment PayrollRun revision contract missing: {marker}")

for marker in (
    "const workflow = context.workflow || {};",
    "workflow.canCalculate",
    "workflow.canSubmitReview",
    "workflow.canReturnForChanges",
    "workflow.canApprove",
    "const actions=new Set(activeBatch?.allowedActions||[]);",
    "data-payment-cancel-batch",
    "data-payment-reopen-batch",
    "actions.has('import_results')",
    "state.payrollLoadedPeriods.delete(label);",
    "delete state.payrollContexts[label];",
):
    if marker not in JS:
        raise SystemExit(f"Internal payroll browser lifecycle authority missing: {marker}")

for forbidden in (
    "['Prepared','Exported'].includes(batch.status)",
    "['Processing','Partially Paid','Needs Attention'].includes(batch.status)",
    "batch.status==='Paid'",
):
    if forbidden in JS:
        raise SystemExit(f"Internal salary-payment UI returned to display-status action inference: {forbidden}")

for marker in (
    "test_internal_payroll_workflow_is_server_authoritative_and_revisioned",
    "test_payment_batch_actions_and_payroll_revision_follow_server_lifecycle",
):
    source = payroll_tests if "internal_payroll_workflow" in marker else payment_tests
    if marker not in source:
        raise SystemExit(f"Internal payroll lifecycle regression test missing: {marker}")

print("Verified Internal Payroll lifecycle and payment action authority contracts.")

# Rental Manpower lifecycle authority contract (1.0.56). Settlement/payment actions
# must be published by backend selectors and settlement revisions must advance through
# finance/payment lifecycle mutations. Historical finance completion remains valid
# after operational supplier/project stop boundaries.
rental_settlement_service = (ROOT / "apps/rental_manpower/services/settlements.py").read_text(encoding="utf-8")
rental_settlement_selector = (ROOT / "apps/rental_manpower/selectors/settlements.py").read_text(encoding="utf-8")
rental_settlement_tests = (ROOT / "apps/rental_manpower/tests/test_settlements.py").read_text(encoding="utf-8")

for marker in (
    '"submit_for_review": "submit"',
    '"return_for_changes": "return"',
    '"close_period": "close"',
    '"complete": SupplierPaymentStatus.PAID',
    'row.revision += 1',
    'settlement.revision += 1',
):
    if marker not in rental_settlement_service:
        raise SystemExit(f"Rental settlement lifecycle service contract missing: {marker}")

for marker in (
    'def settlement_allowed_actions(',
    'def supplier_payment_allowed_actions(',
    'def project_settlement_workflow(',
    '"allowedActions": settlement_allowed_actions(settlement, membership=membership)',
    'allowed_actions = supplier_payment_allowed_actions(payment, membership=membership)',
    '"allowedActions": allowed_actions',
    '"canRetry": "retry" in allowed_actions',
    '"canRecordSupplierInvoice": settlement.status in {RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID}',
    '"supplierInvoice": {',
    '"payable": str(payable)',
    '"canGenerateReceipt": payment.status == SupplierPaymentStatus.PAID',
    '"projectWorkflows": project_workflows',
):
    if marker not in rental_settlement_selector:
        raise SystemExit(f"Rental settlement selector authority contract missing: {marker}")

for marker in (
    'function rentalSettlementProjectWorkflow(',
    'const workflow=rentalSettlementProjectWorkflow(project.id,state.period);',
    'const allowedActions=new Set(workflow.allowedActions||[]);',
    "if (!allowed.has(action))",
    "const actions=new Set(payment.allowedActions||[]);",
    'payment.canRetry?',
    'row.canRetry?',
    'row.canPay&&row.available>.005',
    "{label:'Payment',states:['Payment Processing','Partially Paid','Paid']}",
    "{label:'Closed',states:['Closed']}",
):
    if marker not in JS:
        raise SystemExit(f"Rental browser lifecycle authority missing: {marker}")

for forbidden in (
    "const next = groupStatus==='Draft' ? 'Calculated'",
    "payment.status==='Processing'||payment.status==='Paid'?'supplier-payment-result'",
    "['Failed','Reversed'].includes(row.status)?`<button class=\"btn btn--ghost btn--sm\" data-supplier-payment-retry",
    'function rentalSettlementHasDrift() { return false; }',
):
    if forbidden in JS:
        raise SystemExit(f"Rental UI returned to display-status action inference: {forbidden}")

for marker in (
    'test_rental_settlement_and_payment_actions_are_server_authoritative_and_revisioned',
    'test_operational_stop_does_not_block_historical_rental_finance_completion',
):
    if marker not in rental_settlement_tests:
        raise SystemExit(f"Rental lifecycle regression test missing: {marker}")

document_service = (ROOT / "apps/documents/services/documents.py").read_text(encoding="utf-8")
for document_marker in (
    'Settlement documents require an Approved or later supplier settlement.',
    'Supplier Payment Advice requires a Paid supplier payment.',
    'if subtotal != settlement.total_net:',
):
    if document_marker not in document_service:
        raise SystemExit(f"Rental document lifecycle guard missing: {document_marker}")

print("Verified Rental Manpower lifecycle, payment, document, and historical-finance authority contracts.")


# Recoverable cascade / inherited-lifecycle integrity contract (1.0.57).
# Parent Delete may soft-delete owned child masters, while Project lifecycle is an
# inherited operational boundary for assignments rather than ownership of workers.
internal_api = (ROOT / "apps/internal_payroll/api.py").read_text(encoding="utf-8")
rental_api = (ROOT / "apps/rental_manpower/api.py").read_text(encoding="utf-8")
rental_master_selector = (ROOT / "apps/rental_manpower/selectors/masters.py").read_text(encoding="utf-8")
rental_assignment_selector = (ROOT / "apps/rental_manpower/selectors/assignments.py").read_text(encoding="utf-8")
internal_api_tests = (ROOT / "apps/internal_payroll/tests/test_api.py").read_text(encoding="utf-8")
rental_api_tests = (ROOT / "apps/rental_manpower/tests/test_api.py").read_text(encoding="utf-8")
rental_master_tests = (ROOT / "apps/rental_manpower/tests/test_masters.py").read_text(encoding="utf-8")

for marker in (
    "company=request.company, archived=None, deleted=None",
    "inherited lifecycle state instead of re-querying only",
    "test_independent_employee_restore_under_deleted_parent_returns_inherited_delete_state",
):
    source = internal_api_tests if marker.startswith("test_") else internal_api
    if marker not in source:
        raise SystemExit(f"Internal recoverable cascade API contract missing: {marker}")

for marker in (
    "workers_for_company(company=request.company, archived=None, deleted=None)",
    "test_independent_worker_restore_under_deleted_supplier_returns_inherited_delete_state",
):
    source = rental_api_tests if marker.startswith("test_") else rental_api
    if marker not in source:
        raise SystemExit(f"Rental recoverable cascade API contract missing: {marker}")

for marker in (
    '"assignmentLifecycle": {',
    '"projectDeleted": assignment_project_deleted',
    '"operational": assignment_project_active if assignment_project else True',
    'or (assignment_project is not None and not assignment_project_active)',
):
    if marker not in rental_master_selector:
        raise SystemExit(f"Rental project inherited-lifecycle contract missing: {marker}")

for marker in (
    '"projectArchived": bool(assignment.project.archived_at)',
    '"projectDeleted": bool(assignment.project.deleted_at)',
    '"projectOperational": bool(',
):
    if marker not in rental_assignment_selector:
        raise SystemExit(f"Rental assignment project-lifecycle payload missing: {marker}")

for marker in (
    "const fallbackProject = current.projectId ? {",
    "projectOperational:true",
    "Project deleted · assignment retained for recovery/history",
    "Retained project assignment",
    "snapshot.projectOperational ?",
):
    if marker not in JS:
        raise SystemExit(f"Rental project cascade UI contract missing: {marker}")

for marker in (
    "test_project_delete_stops_current_assignment_without_deleting_worker_and_restore_resumes_exact_assignment",
    'self.assertTrue(deleted_payload["assignmentLifecycle"]["projectDeleted"])',
    'self.assertTrue(restored_payload["assignmentLifecycle"]["operational"])',
):
    if marker not in rental_master_tests:
        raise SystemExit(f"Rental project cascade regression test missing: {marker}")

if "self.assertIsNone(employee.deleted_at)" in internal_api_tests[internal_api_tests.find("def test_department_delete_cascades_current_employee_visibility"):internal_api_tests.find("def test_independent_employee_restore_under_deleted_parent_returns_inherited_delete_state")]:
    raise SystemExit("Department Delete API regression test returned to non-cascading employee expectation.")

print("Verified Archive/Delete/Restore cascade integrity and inherited project lifecycle contracts.")
