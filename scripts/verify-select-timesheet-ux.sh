#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { printf 'select/timesheet UX verification failed: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" text="$2"
  grep -Fq -- "$text" "$ROOT/$file" || fail "$file is missing: $text"
}
reject_text() {
  local file="$1" text="$2"
  if grep -Fq -- "$text" "$ROOT/$file"; then
    fail "$file still contains superseded Payroll override: $text"
  fi
}

[[ -f "$ROOT/static/platform/css/select-controls.css" ]] || fail 'shared select stylesheet is missing'
[[ -f "$ROOT/static/payroll/css/v2/payroll-controls.css" ]] || fail 'canonical Payroll control stylesheet is missing'
require_text templates/base.html "platform/css/select-controls.css"
require_text templates/payroll/app.html "platform/css/select-controls.css"
require_text templates/payroll/app.html "payroll/css/v2/payroll-controls.css"
require_text templates/payroll/app.html "?v=1.0.24"

# Shared file is intentionally cross-app only.
require_text static/platform/css/select-controls.css "appearance: none;"
require_text static/platform/css/select-controls.css "--platform-select-chevron"
require_text static/platform/css/select-controls.css ".ui-v2-compact-select select:not([multiple]):not([size])"
reject_text static/platform/css/select-controls.css "payment-supplier-toolbar"
reject_text static/platform/css/select-controls.css "Internal Payroll operational dropdown convergence"

# Payroll owns one last-loaded operational contract.
require_text static/payroll/css/v2/payroll-controls.css "Payroll control contract — canonical runtime authority."
require_text static/payroll/css/v2/payroll-controls.css "select.ui-v2-payroll-operational-select:not([multiple]):not([size])"
require_text static/payroll/css/v2/payroll-controls.css "--payroll-control-h: 42px;"
require_text static/payroll/css/v2/payroll-controls.css "select.ui-v2-payroll-dense-select"
require_text static/payroll/css/v2/payroll-controls.css ".payment-supplier-toolbar #paymentSupplierFilter.ui-v2-payroll-operational-select"
require_text static/payroll/css/v2/payroll-controls.css ".payment-register-toolbar.ui-v2-payroll-control-toolbar"
require_text static/payroll/css/v2/payroll-controls.css ".ui-v2-payroll-run-toolbar.ui-v2-payroll-control-toolbar"
require_text static/payroll/css/v2/payroll-controls.css ".ui-v2-payroll-operational-filter"
require_text static/payroll/css/v2/payroll-controls.css ".ui-v2-payroll-control-toolbar select:not([multiple]):not([size]):not(.ui-v2-payroll-dense-select):not(.table-select)"

# Runtime normalization removes the legacy compact class from business filters.
require_text static/payroll/js/app.js "function applyPayrollControlClasses(root = pageRoot)"
require_text static/payroll/js/app.js "select.classList.remove('compact-select', 'ui-v2-payroll-compact-select', 'ui-v2-payroll-dense-select')"
require_text static/payroll/js/app.js "select.classList.add('ui-v2-select', 'ui-v2-payroll-operational-select')"
require_text static/payroll/js/app.js "select.classList.add('ui-v2-select', 'ui-v2-payroll-dense-select')"
require_text static/payroll/js/app.js "applyPayrollControlClasses(pageRoot);"
require_text static/payroll/js/app.js 'id="paymentSupplierFilter"'
require_text static/payroll/js/app.js 'class="ui-v2-select ui-v2-payroll-operational-select" id="paymentSupplierFilter"'

# Only deliberate dense controls may keep the compact geometry semantics.
if grep -Eq 'class="[^"]*(compact-select|ui-v2-payroll-compact-select)[^"]*"' "$ROOT/static/payroll/js/app.js"; then
  fail 'Payroll JS still emits a legacy compact-select class; use operational/dense control classes instead.'
fi

# Payment toolbar geometry must have one owner only. Old declarations here were
# the source of the skinny/full-width cascade regression.
for legacy_css in \
  static/payroll/css/components.css \
  static/payroll/css/responsive.css \
  static/payroll/css/production-polish.css \
  static/platform/css/select-controls.css; do
  if grep -Eq 'payment-(supplier|register)-toolbar' "$ROOT/$legacy_css"; then
    fail "$legacy_css still owns payment toolbar geometry; keep it only in payroll-controls.css"
  fi
done

# Today-aware timesheet selection remains intact.
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

printf 'Shared select baseline + canonical Payroll operational/dense control contract verified.\n'
