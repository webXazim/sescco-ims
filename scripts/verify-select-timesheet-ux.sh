#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { printf 'select/timesheet UX verification failed: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" text="$2"
  grep -Fq -- "$text" "$ROOT/$file" || fail "$file is missing: $text"
}

[[ -f "$ROOT/static/platform/css/select-controls.css" ]] || fail 'shared select stylesheet is missing'
require_text templates/base.html "platform/css/select-controls.css"
require_text templates/payroll/app.html "platform/css/select-controls.css"
require_text static/platform/css/select-controls.css "appearance: none;"
require_text static/platform/css/select-controls.css "--platform-select-chevron"
require_text static/platform/css/select-controls.css "select.ui-v2-select:not([multiple]):not([size])"
require_text static/platform/css/select-controls.css "min-height: 40px !important;"
require_text static/platform/css/select-controls.css ".ui-v2-payroll-timesheet-command-strip select"
require_text static/platform/css/select-controls.css "min-height: 38px !important;"
require_text static/platform/css/select-controls.css "select.table-select:not([multiple]):not([size])"
require_text static/payroll/js/app.js "function defaultTimesheetDay(periodLabel)"
require_text static/payroll/js/app.js "return companyTodayDay;"
require_text static/payroll/js/app.js "rentalTimesheetBulkDay: defaultTimesheetDay"
require_text static/payroll/js/app.js "timesheetBulkDay: defaultTimesheetDay"
require_text static/payroll/js/app.js "state.rentalTimesheetBulkDay = defaultTimesheetDay(state.period);"
require_text static/payroll/js/app.js "state.timesheetBulkDay = defaultTimesheetDay(state.period);"
require_text static/payroll/js/app.js "· Today"

if command -v node >/dev/null 2>&1; then
  node --check "$ROOT/static/payroll/js/app.js"
fi

printf 'Shared select controls, production control heights and today-aware timesheet day selection verified.\n'
