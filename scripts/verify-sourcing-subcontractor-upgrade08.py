#!/usr/bin/env python3
"""Upgrade 08 source-only invariants; execute Django tests in staging Docker."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def require(path, *tokens):
    source = (ROOT / path).read_text(encoding="utf-8")
    for token in tokens:
        assert token in source, f"{path}: missing {token!r}"
    if path.endswith(".py"):
        ast.parse(source, filename=path)
    return source


exchange = require(
    "apps/sourcing/exchange.py", '"subcontractors": [', '"services": [',
    '"subcontractor_service_catalog": [', "def _upsert_subcontractor(",
    "def _upsert_service(", "def _upsert_subcontractor_service_catalog(",
    '"subcontractors": _upsert_subcontractor', '"services": _upsert_service',
    '"subcontractor_service_catalog": _upsert_subcontractor_service_catalog',
    "def build_import_template(", "scope_description__iexact=scope",
    "service_location__iexact=location", "transaction.set_rollback(True)",
    "SourcingSubcontractor.objects.for_company(company)",
    "SourcingService.objects.for_company(company)",
    "SourcingSubcontractorService.objects.for_company(company)",
    "verified_now = _bool", "_safe_export_cell(value)",
)
for forbidden in ("from apps.inventory", "from apps.projects", "from apps.data_exchange",
                  "from apps.documents", "from apps.rental_manpower", "from apps.internal_payroll"):
    assert forbidden not in exchange
views = require(
    "apps/sourcing/views.py", "def data_import_template(",
    "membership_can_manage_subcontractor_sourcing(membership)",
    "membership_can_view_subcontractor_sourcing(membership)",
    "membership_can_manage_sourcing_masters(membership)",
    "membership_can_export_sourcing(membership)",
    "if not _can_import_dataset(_membership(request), dataset):",
)
require("apps/sourcing/urls.py", '"data-exchange/template/<str:dataset>/"')
require("templates/sourcing/data_exchange.html", "Blank import templates", "Import CSV / XLSX", "verified_now=yes")
for t in ("subcontractors/list.html", "services/list.html"):
    require("templates/sourcing/" + t, "data-sourcing-export-current")
require("templates/sourcing/subcontractors/_offers.html", "data-sourcing-finder-root", "data-sourcing-live-finder")
require("templates/sourcing/sidebar.html", "SOURCING_ACCESS.subcontractors.manage")
require("apps/sourcing/tests/test_subcontractor_data_exchange.py",
        "test_master_dry_run_then_commit", "test_catalog_multi_scope_verification",
        "test_duplicate_catalog_identity", "test_cross_company_service_code",
        "test_view_only_export_authorization", "test_filtered_service_catalog_export",
        "test_new_dataset_import_template_xlsx")
print("PASS: Upgrade 08 three-dataset sourcing exchange, tenant/permission guards, template/export surfaces and regression coverage (source only).")
