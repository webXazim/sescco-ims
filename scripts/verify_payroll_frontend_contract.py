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
