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
[[ -f static/payroll/css/v2/payroll-controls.css ]] || fail "Canonical Payroll control stylesheet is missing."
[[ -f templates/payroll/app.html ]] || fail "Payroll Django shell template is missing."
[[ -f apps/core/payroll_views.py ]] || fail "Payroll shell bootstrap view is missing."

grep -Fq 'path("payroll/", payroll_app, name="payroll")' apps/core/urls.py \
  || fail "The /app/payroll/ workspace route is not mounted."
grep -Fq "payroll/css/v2/index.css" templates/payroll/app.html \
  || fail "Payroll shell is not using namespaced V2 CSS."
grep -Fq "payroll/js/app.js" templates/payroll/app.html \
  || fail "Payroll shell is not using the namespaced JS bundle."
grep -Fq "payroll/css/v2/payroll-controls.css" templates/payroll/app.html \
  || fail "Payroll shell is not loading the canonical control stylesheet."
if grep -Eq "static ['\"](css|js)/" templates/payroll/app.html; then
  fail "Payroll template references an un-namespaced root CSS/JS asset."
fi

python3 - <<'PY_ORDER'
from pathlib import Path
text = Path('templates/payroll/app.html').read_text(encoding='utf-8')
shared = text.index("platform/css/select-controls.css")
validation = text.index("platform/css/form-validation.css")
canonical = text.index("payroll/css/v2/payroll-controls.css")
assert shared < canonical and validation < canonical, "canonical Payroll controls must load after shared/platform form CSS"
assert "?v=1.0.25" in text, "Payroll control asset must carry the 1.0.25 cache buster"
PY_ORDER

printf 'Checking Payroll workspace navigation contract...\n'
grep -Fq "?workspace=internal#/overview" templates/payroll/app.html \
  || fail "Internal Payroll workspace is missing its reload-safe URL."
grep -Fq "?workspace=rental#/overview" templates/payroll/app.html \
  || fail "Rental Manpower workspace is missing its reload-safe URL."
grep -Fq "?workspace=management#/overview" templates/payroll/app.html \
  || fail "Management workspace is missing its reload-safe URL."
grep -Fq 'access_context["initial_workspace"] = initial_workspace' apps/core/payroll_views.py \
  || fail "Payroll server does not validate/publish the requested initial workspace."
grep -Fq 'function initWorkspaceSwitcher()' static/payroll/js/app.js \
  || fail "Payroll workspace switcher is not initialized independently of sidebar behavior."
grep -Fq 'return serverWorkspaces.includes(workspace);' static/payroll/js/app.js \
  || fail "Payroll workspace authorization is not using the request-specific server workspace list."
grep -Fq "if (location.hash === target)" static/payroll/js/app.js \
  || fail "Payroll same-hash workspace navigation cannot force an immediate redraw."
grep -Fq '.ui-v2-root [data-dropdown].is-open > [data-dropdown-menu]' static/platform/css/payroll-shell-fixes.css \
  || fail "Open Payroll dropdown menus do not restore pointer interaction."
grep -Fq 'pointer-events: auto !important;' static/platform/css/payroll-shell-fixes.css \
  || fail "Open Payroll dropdown menus can still pass clicks through to page content."

printf 'Checking imported Payroll frontend asset hashes...\n'
sha256sum -c merge/payroll-frontend-assets.sha256 >/dev/null \
  || fail "A frozen Payroll frontend asset changed. Update only in an explicit frontend upgrade."

printf 'Checking Payroll CSS import graph...\n'
python3 - <<'PY'
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
python3 scripts/verify_payroll_frontend_contract.py

printf 'Payroll frontend integration verified.\n'
