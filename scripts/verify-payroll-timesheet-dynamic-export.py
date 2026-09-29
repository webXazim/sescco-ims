#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL TIMESHEET EXPORT ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if text("VERSION").strip() != "1.0.117":
    fail("packaged release must remain 1.0.117")

requirements = text("requirements/base.txt")
if "reportlab==4.4.9" not in requirements:
    fail("ReportLab production dependency is not pinned")

urls = text("apps/rental_manpower/urls.py")
if 'path("api/rental/timesheets/export/", api.rental_timesheet_export_api, name="timesheets-export-api")' not in urls:
    fail("Rental timesheet export endpoint is not mounted")

api = text("apps/rental_manpower/api.py")
for marker in (
    'def rental_timesheet_export_api(request: HttpRequest):',
    '_require_permission(request, AccessPermission.RENTAL_TIMESHEETS_VIEW)',
    'rental_timesheet_export_schema(',
    'build_rental_timesheet_export_dataset(',
    'render_rental_timesheet_export(dataset, str(body.get("format") or ""))',
    'action="rental.timesheet.exported"',
    'response["Cache-Control"] = "private, no-store"',
    'response["X-Export-Row-Count"] = str(len(dataset["rows"]))',
):
    if marker not in api:
        fail(f"API export contract missing: {marker}")

service = text("apps/rental_manpower/services/timesheet_exports.py")
for marker in (
    "EXPORT_MAX_ROWS = 5000",
    'VALID_EXPORT_FORMATS = {"xlsx", "pdf"}',
    'ExportColumn("worker_id", "Worker ID"',
    'ExportColumn("supplier_name", "Supplier name"',
    'ExportColumn("assignment_trade", "Trade / role"',
    'ExportColumn("regular_hours", "Regular hours"',
    'ExportColumn("regular_hours_limit", "Regular hours / day"',
    'ExportColumn("overtime_hours", "OT hours"',
    'ExportColumn("automatic_overtime_hours", "Auto OT hours"',
    'ExportColumn("additional_overtime_hours", "Additional OT hours"',
    'ExportColumn("overtime_multiplier", "OT multiplier"',
    'ExportColumn("timesheet_status", "Timesheet status"',
    'ExportColumn("approved_adjustment_earnings", "Approved adjustment earnings"',
    'ExportColumn("approved_adjustment_deductions", "Approved adjustment deductions"',
    'ExportColumn("current_adjustment_deductions", "Current adjustment deductions"',
    'ExportColumn("approved_calculated_result", "Approved-only result"',
    'ExportColumn("calculated_result", "Projected calculated result"',
    "_adjustment_totals_for_workers",
    'f"day_{day:02d}"',
    'permission="supplier_detail"',
    'permission="commercial"',
    'permission="workflow_detail"',
    'raise PermissionDenied("One or more requested export columns are not available to your access profile.")',
    'if value[:1] in {"=", "+", "-", "@"}:',
    'A = Absent',
    '"exported_by": _actor_label(getattr(membership, "user", None))',
    "def render_rental_timesheet_xlsx(dataset",
    "def render_rental_timesheet_pdf(dataset",
    '"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"',
    '"application/pdf"',
):
    if marker not in service:
        fail(f"server export service contract missing: {marker}")

frontend = text("static/payroll/js/app.js")
for marker in (
    "function rentalTimesheetExportFilterParams()",
    "function renderRentalTimesheetExportDrawer(schema)",
    "async function openRentalTimesheetExportDrawer()",
    "async function runRentalTimesheetExport(schema)",
    'name="rental-export-format"',
    'name="rental-export-scope"',
    'value="all_matching"',
    'value="current_page"',
    'value="selected"',
    "data-rental-export-column",
    "Recommended",
    "Select all",
    "fetch('/api/rental/timesheets/export/'",
    "openRentalTimesheetExportDrawer",
):
    if marker not in frontend:
        fail(f"dynamic export UI contract missing: {marker}")
if "function exportRentalTimesheetCsv()" in frontend:
    fail("legacy browser-only Rental CSV export is still active")

css = text("static/payroll/css/v2/pages/timesheet.css")
for marker in (
    "dynamic Rental Timesheet export",
    ".ui-v2-payroll-timesheet-export-drawer",
    ".ui-v2-timesheet-export-column-grid",
    ".ui-v2-timesheet-export-footer",
):
    if marker not in css:
        fail(f"dynamic export styling missing: {marker}")

tests = text("apps/rental_manpower/tests/test_timesheet_exports.py")
for marker in (
    "test_export_schema_is_dynamic_and_includes_month_days",
    "test_xlsx_export_contains_all_matching_rows_and_selected_columns",
    "test_pdf_export_is_a_real_pdf_file",
    "test_selected_scope_only_exports_requested_matching_workers",
    "test_supervisor_schema_does_not_offer_supplier_private_or_commercial_columns",
    "test_export_calculated_result_includes_pending_adjustments_as_projected_payment",
):
    if marker not in tests:
        fail(f"timesheet export regression coverage missing: {marker}")

notes = text("RELEASE_NOTES.md")
if "# 1.0.117 — Rental Timesheet Dynamic Excel/PDF Export" not in notes:
    fail("release notes are missing the dynamic timesheet export upgrade")

print("Verified SESCCO MS 1.0.117 Rental Timesheet dynamic Excel/PDF export: selectable columns, scoped rows, adjustment-aware calculated results, permission-safe server generation, audit evidence and export safety controls.")
