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
    "class RentalTimesheetPeriodPolicy",
    "off_weekdays = models.JSONField",
    "regular_hours_per_day = models.DecimalField",
    "overtime_multiplier = models.DecimalField",
    "automatic_overtime = models.BooleanField",
    "default_rental_timesheet_off_weekdays",
)
require(
    "apps/rental_manpower/models/__init__.py",
    "from .timesheet_settings import RentalTimesheetPeriodPolicy, RentalTimesheetProjectSettings",
)
require(
    "apps/rental_manpower/migrations/0010_rental_timesheet_project_settings.py",
    'name="RentalTimesheetProjectSettings"',
    '"off_weekdays"',
)
require(
    "apps/rental_manpower/migrations/0011_timesheet_working_hours_overtime_policy.py",
    'name="RentalTimesheetPeriodPolicy"',
    'name="regular_hours_per_day"',
    'name="overtime_multiplier"',
    'name="automatic_overtime"',
    "backfill_period_policies",
)
require(
    "apps/rental_manpower/services/timesheet_policy.py",
    "DEFAULT_REGULAR_HOURS_PER_DAY",
    "DEFAULT_OVERTIME_MULTIPLIER",
    "ensure_period_timesheet_policy",
    "split_daily_hours",
    "overtime_bill_rate",
)
require(
    "apps/rental_manpower/api.py",
    "def rental_timesheet_settings_api",
    'AccessPermission.RENTAL_TIMESHEETS_EDIT',
    'action="rental.timesheet.settings_updated"',
    '"regular_hours_per_day"',
    '"overtime_multiplier"',
    '"automatic_overtime"',
    "ensure_period_timesheet_policy",
)
require(
    "apps/rental_manpower/urls.py",
    'path("api/rental/timesheets/settings/"',
)
require(
    "apps/rental_manpower/selectors/timesheets.py",
    '"offWeekdays": off_weekdays',
    '"regularHoursPerDay": str(regular_hours)',
    '"automaticOvertime": automatic_overtime',
    '"overtimeMultiplier": str(multiplier)',
    '"policyLocked": policy_locked',
    '"canViewCommercial"',
    '"canViewAdjustments"',
    '"canViewCalculatedResult"',
    '"adjustmentSummary"',
    "def _rental_timesheet_adjustment_summary",
    '.annotate(total=Sum("amount"), row_count=Count("id"))',
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
    "Adjustment +",
    "Adjustment −",
    "Calculated result",
    "showCalculatedResult",
    "data-rental-show-calculated-result",
    "Gross wage + approved adjustment earnings − approved deductions = calculated result.",
    "negative · settlement blocked",
    "function bindRentalTimesheetBoardResizers()",
    "data-rental-board-resize",
    "function renderRentalTimesheetSettingsDrawer()",
    "Working hours & overtime",
    "data-rental-regular-hours",
    "data-rental-auto-overtime",
    "data-rental-overtime-multiplier",
    "data-rental-overtime-premium",
    "OT premium %",
    "1.5% becomes 1.015×",
    "Same · 1.00×",
    "+50% · 1.50×",
    "Automatic daily excess + additional OT",
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
    ".ui-v2-prs-timesheet-policy-grid",
    ".ui-v2-prs-timesheet-policy-presets",
    ".ui-v2-prs-timesheet-calculated-settings",
    ".ui-v2-prs-rental-calculated-result",
    "thead th.is-project-offday::after",
    "tbody td.is-project-offday",
)
require(
    "apps/rental_manpower/services/timesheet_exports.py",
    'ExportColumn("total_hours"',
    'ExportColumn("base_wage"',
    'ExportColumn("overtime_wage"',
    'ExportColumn("gross_wage"',
    'ExportColumn("approved_adjustment_earnings"',
    'ExportColumn("approved_adjustment_deductions"',
    'ExportColumn("calculated_result"',
    "_adjustment_totals_for_workers",
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

require(
    "apps/rental_manpower/tests/test_timesheets.py",
    "test_timesheet_context_returns_permission_safe_approved_and_pending_adjustment_preview",
)
require(
    "apps/rental_manpower/tests/test_timesheet_exports.py",
    "test_export_calculated_result_applies_only_approved_adjustments",
)

print("Rental timesheet board/settings/calculated-result contract verified.")
