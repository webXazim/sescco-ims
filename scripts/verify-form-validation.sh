#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { printf 'form-validation verification failed: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" text="$2"
  grep -Fq -- "$text" "$ROOT/$file" || fail "$file is missing: $text"
}
reject_text() {
  local file="$1" text="$2"
  if grep -Fq -- "$text" "$ROOT/$file"; then fail "$file still contains forbidden text: $text"; fi
}

[[ -f "$ROOT/static/platform/css/form-validation.css" ]] || fail "shared form-validation CSS is missing"
[[ -f "$ROOT/static/platform/js/form-validation.js" ]] || fail "shared form-validation JavaScript is missing"

require_text templates/base.html "platform/css/form-validation.css"
require_text templates/base.html "platform/js/form-validation.js"
require_text templates/payroll/app.html "platform/css/form-validation.css"
require_text templates/payroll/app.html "platform/js/form-validation.js"
require_text templates/registration/login.html "platform/css/form-validation.css"
require_text templates/registration/login.html "platform/js/form-validation.js"
require_text templates/partials/form_field.html "field.field.required"
require_text templates/partials/form_field.html "is-invalid"

require_text static/platform/js/form-validation.js "validateRequired"
require_text static/platform/js/form-validation.js "field-required-message"
require_text static/platform/js/form-validation.js "aria-invalid"
require_text static/platform/js/form-validation.js "syncConditionalRequired"
require_text apps/projects/forms.py "data-required-when-name"
require_text static/platform/css/form-validation.css ".required::after"
require_text static/platform/css/form-validation.css ".field-required-message"
require_text templates/explorer/saved_view_row.html 'for="saved-view-name-{{ saved.pk }}"'
reject_text templates/inventory/delete_confirm.html '<b>*</b>'

require_text static/payroll/js/app.js "payrollRequiredFieldNames"
require_text static/payroll/js/app.js "validatePayrollRequiredFields"
require_text static/payroll/js/app.js "supplier-name"
require_text static/payroll/js/app.js "employee-name"
require_text static/payroll/js/app.js "rental-worker-name"
require_text static/payroll/js/app.js "project-name"
require_text static/payroll/js/app.js "Your sign-in session is no longer active. Sign in again to continue."

while IFS= read -r file; do
  reject_text "${file#"$ROOT/"}" "Authentication is required."
done < <(find "$ROOT/apps" "$ROOT/static" "$ROOT/templates" -type f \( -name '*.py' -o -name '*.js' -o -name '*.html' \) -print)

printf 'Project-wide required-field validation contract verified.\n'
