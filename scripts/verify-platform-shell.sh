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
grep -Fq 'class="platform-account"' templates/partials/sidebar.html \
  || fail "Inventory shell is missing the compact account drop-up."
grep -Fq '.platform-account__menu' static/platform/css/shell-switchers.css \
  || fail "Shared shell CSS is missing the account drop-up styling."
grep -Fq 'No changes should be assumed successful.' templates/500.html \
  || fail "The shared 500 page still uses module-specific failure wording."
grep -Fq '{% if not SINGLE_COMPANY_MODE and ACTIVE_COMPANY %}' templates/partials/platform_switchers.html \
  || fail "Legacy company switching is not safely hidden behind single-company mode."
grep -Fq '<small>Module</small>' templates/partials/platform_switchers.html \
  || fail "Shared switcher is not using module terminology."
grep -Fq 'if settings.SINGLE_COMPANY_MODE:' apps/accounts/services.py \
  || fail "Company activation endpoint is not guarded in single-company mode."

if grep -Fq '<span>Payroll Management</span></a>' templates/partials/sidebar.html; then
  fail "Legacy Payroll navigation link remains inside the Inventory module nav."
fi
if grep -Fq '<button class="text-button" type="submit">Sign out</button>' templates/partials/sidebar.html; then
  fail "Legacy inline Inventory sign-out control remains in the sidebar footer."
fi
if grep -Fq 'Open the Inventory workspace' templates/payroll/app.html; then
  fail "Temporary Inventory account-menu bridge remains in the Payroll shell."
fi

grep -Fq "brand-sescco-mark.webp" templates/partials/sidebar.html \
  || fail "Inventory shell is not using the SESCCO mark."
grep -Fq "brand-sescco-mark.webp" templates/payroll/app.html \
  || fail "Payroll shell is not using the SESCCO mark."
grep -Fq "SESCCO MS" templates/registration/login.html \
  || fail "Authentication surface is not branded as SESCCO MS."

sha256sum -c merge/platform-shell-assets.sha256 >/dev/null \
  || fail "A frozen Upgrade 10 platform-shell asset changed."

if command -v node >/dev/null 2>&1; then
  node --check static/platform/js/shell-switchers.js
fi

printf 'Unified platform shell verified.\n'
