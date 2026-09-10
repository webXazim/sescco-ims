#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

fail() {
  printf 'PAYROLL FRONTEND ERROR: %s\n' "$*" >&2
  exit 1
}

printf 'Checking merged Payroll frontend namespace...\n'
[[ -f static/payroll/js/app.js ]] || fail "static/payroll/js/app.js is missing."
[[ -f static/payroll/css/v2/index.css ]] || fail "Payroll V2 index stylesheet is missing."
[[ -f static/payroll/css/v2/prs-final.css ]] || fail "Payroll final cutover stylesheet is missing."
[[ -f templates/payroll/app.html ]] || fail "Payroll Django shell template is missing."
[[ -f apps/core/payroll_views.py ]] || fail "Payroll shell bootstrap view is missing."

grep -Fq 'path("payroll/", payroll_app, name="payroll")' apps/core/urls.py \
  || fail "The /app/payroll/ workspace route is not mounted."
grep -Fq "payroll/css/v2/index.css" templates/payroll/app.html \
  || fail "Payroll shell is not using namespaced V2 CSS."
grep -Fq "payroll/js/app.js" templates/payroll/app.html \
  || fail "Payroll shell is not using the namespaced JS bundle."
if grep -Eq "static ['\"](css|js)/" templates/payroll/app.html; then
  fail "Payroll template references an un-namespaced root CSS/JS asset."
fi

printf 'Checking imported Payroll frontend asset hashes...\n'
sha256sum -c merge/payroll-frontend-assets.sha256 >/dev/null \
  || fail "A frozen Payroll frontend asset changed. Update only in an explicit frontend upgrade."

printf 'Checking Payroll CSS import graph...\n'
python - <<'PY'
import re
from pathlib import Path

root = Path('static/payroll/css')
missing = []
for css in root.rglob('*.css'):
    text = css.read_text(encoding='utf-8')
    for target in re.findall(r'@import\s+["\']([^"\']+)["\']', text):
        if target.startswith(('http:', 'https:', 'data:')):
            continue
        resolved = (css.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            missing.append(f'{css}: import escapes Payroll namespace: {target}')
            continue
        if not resolved.is_file():
            missing.append(f'{css}: missing {target}')
if missing:
    raise SystemExit('\n'.join(missing))
PY

if command -v node >/dev/null 2>&1; then
  node --check static/payroll/js/app.js
fi

printf 'Checking Payroll browser/API URL contract...\n'
python scripts/verify_payroll_frontend_contract.py

printf 'Payroll frontend integration verified.\n'
