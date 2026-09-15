#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def fail(message: str) -> None: raise SystemExit(f"PAYROLL DRAWER SELECTOR SCALE ERROR: {message}")
def text(rel: str) -> str:
    p=ROOT/rel
    if not p.is_file(): fail(f"missing file: {rel}")
    return p.read_text(encoding="utf-8")

if text("VERSION").strip() != "1.0.86": fail("VERSION must be 1.0.86")
contract=json.loads(text("merge/payroll-drawer-selector-scale.json"))
if contract.get("release") != "1.0.86": fail("drawer selector contract release must be 1.0.86")
lookup=contract.get("lookup_contract") or {}
for key,expected in {
    "dropdown_page_size":10,"max_results_per_request":25,"master_minimum_query_chars":2,
    "exact_count_query":False,"page_size_plus_one":True,"abort_stale_requests":True,
    "search_inside_dropdown":True,"save_posts_selected_uuid":True,"backend_revalidation_authoritative":True,
}.items():
    if lookup.get(key) != expected: fail(f"lookup contract changed: {key}")

internal_urls=text("apps/internal_payroll/urls.py");internal_api=text("apps/internal_payroll/api.py")
for needle in ("api/internal/lookups/organization/","api/internal/lookups/employees/","organization_lookup_api","employee_lookup_api"):
    if needle not in internal_urls: fail(f"internal bounded lookup route missing: {needle}")
for needle in ("def _lookup_page","page_size = min(25","start + page_size + 1","len(query) < min_query","def organization_lookup_api","def employee_lookup_api"):
    if needle not in internal_api: fail(f"internal lookup lost bounded behavior: {needle}")
for fn,next_fn in (("def organization_lookup_api","def employee_lookup_api"),("def employee_lookup_api","def branches_api")):
    block=internal_api[internal_api.index(fn):internal_api.index(next_fn)]
    if "Paginator(" in block or ".count()" in block or "serialize_list(" in block: fail(f"{fn} regressed to exact-count pagination")

rental_urls=text("apps/rental_manpower/urls.py");rental_api=text("apps/rental_manpower/api.py")
for needle in ("api/rental/suppliers/lookup/","api/rental/supplier-payments/settlement-lookup/","supplier_lookup_api","supplier_payment_settlement_lookup_api"):
    if needle not in rental_urls: fail(f"rental bounded lookup route missing: {needle}")
for needle in ("def _bounded_lookup_page","page_size = min(25","start + page_size + 1","def supplier_lookup_api","def supplier_payment_settlement_lookup_api","SupplierPaymentStatus.PAID","SupplierPaymentStatus.PROCESSING","RentalSettlementStatus.PARTIALLY_PAID"):
    if needle not in rental_api: fail(f"rental lookup lost bounded/financial behavior: {needle}")
payment_lookup=rental_api[rental_api.index("def supplier_payment_settlement_lookup_api"):rental_api.index("def suppliers_api",rental_api.index("def supplier_payment_settlement_lookup_api"))]
if "total_net__gt=" not in payment_lookup: fail("supplier-payment lookup no longer excludes fully reserved/paid settlements")
if "Paginator(" in payment_lookup or ".count()" in payment_lookup or "serialize_list(" in payment_lookup: fail("supplier-payment lookup must remain count-free")

js=text("static/payroll/js/app.js")
for needle in (
    "function boundedDrawerLookupField","function setupBoundedDrawerLookup","cancelBoundedDrawerLookups",
    "internal-add-branch","internal-add-department","salary-structure-employee","rental-add-supplier",
    "worker-advance-project","supplier-payment-settlement","data-bounded-drawer-lookup=\"document-source\"",
    "/api/internal/lookups/organization/","/api/internal/lookups/employees/","/api/rental/suppliers/lookup/",
    "/api/rental/supplier-payments/settlement-lookup/","/api/rental/adjustments/lookup/","/api/documents/sources/",
    "page_size:'10'","_lookupRequestController?.abort()",
):
    if needle not in js: fail(f"frontend bounded selector behavior missing: {needle}")
for forbidden in ("name=\"document-source-search\"","Find source record"):
    if forbidden in js: fail(f"Finalize Document regressed to separate search + select controls: {forbidden}")

internal_tpl=js[js.index("'internal-employee': {"):js.index("'branch': {",js.index("'internal-employee': {"))]
if "state.branches.filter" in internal_tpl or "state.departments.filter" in internal_tpl or "namedSelectOptions('Department'" in internal_tpl or "namedSelectOptions('Branch / Office'" in internal_tpl:
    fail("Add Internal Employee still hydrates full Branch/Department master selectors")
rental_tpl=js[js.index("'rental-worker': {"):js.index("'project': {",js.index("'rental-worker': {"))]
if "state.suppliers.filter" in rental_tpl or "namedSelectOptions('Manpower supplier'" in rental_tpl:
    fail("Add Rental Worker still hydrates the full supplier master selector")
org=js[js.index("function openEmployeeOrganizationDrawer"):js.index("function openEmployeeEditDrawer")]
if "state.branches.filter" in org or "state.departments.filter" in org or "namedSelectOptions('Branch / Office'" in org:
    fail("Change Organization still renders full organization master selects")
advance=js[js.index("} else if (action === 'advance')",js.index("function openRentalWorkerActionDrawer")):js.index("} else return;",js.index("function openRentalWorkerActionDrawer"))]
if "state.projects.filter" in advance or "namedSelectOptions('Project'" in advance: fail("Worker Advance still renders the full project master")
payment=js[js.index("function openSupplierPaymentDrawer"):js.index("function openSupplierPaymentDetailDrawer")]
if "payables.map" in payment or "<select name=\"supplier-payment-settlement\"" in payment: fail("Supplier Payment still renders full settlement options")
if "state.drawerContext?.settlement" not in js: fail("Supplier Payment save no longer uses the selected bounded lookup row")

bank=js[js.index("function openBankTemplateDrawer"):js.index("function openEmployeePaymentProfileDrawer")]
if "setupRentalAssignmentProjectLookup" in bank: fail("Assignment Project lookup initializer is still misbound to Bank Template")
assignment=js[js.index("function openRentalWorkerActionDrawer"):js.index("function rentalWorkerById")]
if "setupRentalAssignmentProjectLookup" not in assignment: fail("Assignment Project lookup initializer is not attached to Rental Assignment drawer")

for rel,methods in {
    "apps/internal_payroll/tests/test_api.py":["test_drawer_lookup_endpoints_are_bounded_and_count_free","test_employee_lookup_is_thin_bounded_and_search_gated"],
    "apps/rental_manpower/tests/test_api.py":["test_supplier_drawer_lookup_is_search_gated_and_bounded"],
}.items():
    source=text(rel)
    for method in methods:
        if f"def {method}" not in source: fail(f"missing Django regression: {rel}:{method}")

doc_api=text("apps/documents/api.py")
for needle in ("page_size = min(25","start + page_size + 1","hasNext","requires_search"):
    if needle not in doc_api: fail(f"document source lookup lost bounded paging: {needle}")
doc_block=doc_api[doc_api.index("def document_sources_api"):doc_api.index("def document_detail_api")]
if "Paginator(" in doc_block or ".count()" in doc_block: fail("document source lookup must remain count-free")

print("Verified SESCCO MS 1.0.86 cross-workspace drawer selector scale hardening: bounded search-in-dropdown selectors, count-free pages, cancellable requests, financial availability filtering and corrected assignment initializer placement.")
