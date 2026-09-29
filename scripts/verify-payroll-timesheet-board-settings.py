#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *needles: str) -> None:
    text = read(path)
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: missing required timesheet-board contract: {missing}")


require(
    "apps/rental_manpower/models/timesheet_settings.py",
    "class RentalTimesheetProjectSettings",
    "off_weekdays = models.JSONField",
    "default_rental_timesheet_off_weekdays",
)
require(
    "apps/rental_manpower/models/__init__.py",
    "from .timesheet_settings import RentalTimesheetProjectSettings",
)
require(
    "apps/rental_manpower/migrations/0010_rental_timesheet_project_settings.py",
    'name="RentalTimesheetProjectSettings"',
    '"off_weekdays"',
)
require(
    "apps/rental_manpower/api.py",
    "def rental_timesheet_settings_api",
    'AccessPermission.RENTAL_TIMESHEETS_EDIT',
    'action="rental.timesheet.settings_updated"',
)
require(
    "apps/rental_manpower/urls.py",
    'path("api/rental/timesheets/settings/"',
)
require(
    "apps/rental_manpower/selectors/timesheets.py",
    '"offWeekdays": off_weekdays',
    '"canViewCommercial"',
    '"canViewWorkerIdentity"',
    'worker_payload["nationalId"]',
)
require(
    "static/payroll/js/app.js",
    "payroll-ui-rental-timesheet-board-v2",
    "function rentalTimesheetBoardColumnCatalog()",
    "Iqama / National ID",
    "Commercial rate",
    "Basic hrs",
    "OT hrs",
    "Total hrs",
    "Base wage",
    "OT wage",
    "Gross wage",
    "function bindRentalTimesheetBoardResizers()",
    "data-rental-board-resize",
    "function renderRentalTimesheetSettingsDrawer()",
    "Project weekly off days",
    "Apply OFF to blank off-days on this page",
    "data-rental-timesheet-settings",
)
require(
    "static/payroll/css/v2/prs-rental-timesheet-cutover.css",
    ".is-board-left",
    ".is-board-right",
    ".ui-v2-prs-rental-board-resizer",
    ".ui-v2-prs-timesheet-weekdays",
)
require(
    "apps/rental_manpower/services/timesheet_exports.py",
    'ExportColumn("total_hours"',
    'ExportColumn("base_wage"',
    'ExportColumn("overtime_wage"',
    'ExportColumn("gross_wage"',
)
require(
    "apps/core/payroll_views.py",
    "show_management_workspace = can_management and not (can_internal or can_rental)",
    'access_context["payroll_workspaces"] = allowed_workspace_keys',
)
require(
    "templates/payroll/app.html",
    "{% if show_management_workspace %}",
    'data-workspace-switch="management"',
)
require(
    "merge/payroll-data-authority.json",
    "payroll-ui-rental-timesheet-board-v2",
)

print("Rental timesheet board/settings contract verified.")
