#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

fail() {
  printf 'PLATFORM SHELL ERROR: %s\n' "$*" >&2
  exit 1
}

printf 'Checking unified platform shell...\n'
[[ -f templates/partials/platform_switchers.html ]] || fail "Shared platform switcher template is missing."
[[ -f static/platform/css/shell-switchers.css ]] || fail "Shared platform switcher CSS is missing."
[[ -f static/platform/js/shell-switchers.js ]] || fail "Shared platform switcher JS is missing."
[[ -f apps/accounts/modules.py ]] || fail "Platform module authorization helper is missing."

grep -Fq '{% include "partials/platform_switchers.html" %}' templates/partials/sidebar.html \
  || fail "Inventory shell does not include the shared platform switcher."
grep -Fq '{% include "partials/platform_switchers.html" %}' templates/payroll/app.html \
  || fail "Payroll shell does not include the shared platform switcher."
grep -Fq "platform/css/shell-switchers.css" templates/base.html \
  || fail "Inventory base does not load platform shell CSS."
grep -Fq "platform/css/shell-switchers.css" templates/payroll/app.html \
  || fail "Payroll shell does not load platform shell CSS."
grep -Fq "platform/js/shell-switchers.js" templates/base.html \
  || fail "Inventory base does not load platform shell JS."
grep -Fq "platform/js/shell-switchers.js" templates/payroll/app.html \
  || fail "Payroll shell does not load platform shell JS."
grep -Fq 'name="module" value="{{ PLATFORM_CONTEXT.current_module' templates/partials/platform_switchers.html \
  || fail "Company switch does not carry the active module contract."
grep -Fq 'membership_can_module(membership, module)' apps/accounts/views.py \
  || fail "Company switching does not validate destination-module access."

if grep -Fq '<span>Payroll Management</span></a>' templates/partials/sidebar.html; then
  fail "Legacy Payroll navigation link remains inside the Inventory module nav."
fi
if grep -Fq 'Open the Inventory workspace' templates/payroll/app.html; then
  fail "Temporary Inventory account-menu bridge remains in the Payroll shell."
fi

sha256sum -c merge/platform-shell-assets.sha256 >/dev/null \
  || fail "A frozen Upgrade 10 platform-shell asset changed."

if command -v node >/dev/null 2>&1; then
  node --check static/platform/js/shell-switchers.js
fi

printf 'Unified platform shell verified.\n'
