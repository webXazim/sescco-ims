#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" pattern="$2" message="$3"
  grep -Fq -- "${pattern}" "${file}" || fail "${message}"
}

[[ -f merge/production-freeze.sha256 ]] || fail 'Production-freeze manifest is missing.'
sha256sum -c merge/production-freeze.sha256 >/dev/null \
  || fail 'Frozen production source/configuration changed.'

bash scripts/verify-select-timesheet-ux.sh
bash scripts/verify-inventory-explorer-ux.sh
python3 scripts/verify-payroll-reference-coverage.py
python3 scripts/verify-payroll-reference-output.py
python3 scripts/verify-full-demo-seed.py
python3 scripts/verify-lifecycle-authority.py
python3 scripts/verify-employee-lifecycle.py
python3 scripts/verify-organization-lifecycle.py
python3 scripts/verify-rental-master-lifecycle.py
python3 scripts/verify-project-inventory-lifecycle.py
python3 scripts/verify-secondary-configuration-lifecycle.py
python3 scripts/verify-unified-lifecycle-ux.py
python3 scripts/verify-lifecycle-retention-contract.py
python3 scripts/verify-single-company-branding.py
python3 scripts/verify-branding-migration-lineage.py

[[ -f merge/shell-convergence-assets.sha256 ]] || fail 'Shell-convergence manifest is missing.'
sha256sum -c merge/shell-convergence-assets.sha256 >/dev/null \
  || fail 'Unified Inventory/Payroll shell assets changed.'

require_text templates/base.html 'class="inventory-shell-v2"' 'Inventory is not using the converged Payroll-style shell.'
require_text templates/base.html 'platform/css/inventory-shell.css' 'Inventory shell stylesheet is not loaded.'
require_text templates/base.html 'platform/js/inventory-shell.js' 'Inventory shell behavior is not loaded.'
require_text templates/partials/sidebar.html 'data-inventory-sidebar-collapse' 'Inventory shell is missing collapse behavior.'
require_text templates/partials/sidebar.html 'data-inventory-sidebar-resize' 'Inventory shell is missing resize behavior.'
require_text templates/payroll/app.html 'platform/css/payroll-shell-fixes.css' 'Payroll shell focus-mode fix is not loaded.'
require_text static/platform/css/payroll-shell-fixes.css 'body.timesheet-focus-mode .ui-v2-app-shell > .ui-v2-sidebar' 'Payroll focus mode does not hide the V2 sidebar.'
require_text static/platform/css/payroll-shell-fixes.css 'body.timesheet-focus-mode .ui-v2-topbar' 'Payroll focus mode does not hide the V2 topbar.'
require_text static/platform/css/payroll-shell-fixes.css 'margin-left: 0 !important;' 'Payroll focus mode does not remove the sidebar offset.'

require_text merge/source-manifest.json '"completed_upgrade": 12' 'Merge progress is not frozen at Upgrade 12.'
require_text merge/source-manifest.json '"total_upgrades": 12' 'Merge upgrade total changed.'
require_text merge/source-manifest.json '"merge_complete": true' 'Merge is not marked complete.'
require_text merge/source-manifest.json '"next_upgrade": null' 'Final merge state must not declare another merge upgrade.'
require_text merge/source-manifest.json '"production_freeze_manifest": "merge/production-freeze.sha256"' 'Freeze manifest contract is missing.'

require_text docker-compose.rehearsal.yml 'name: ims_merge_rehearsal_postgres_data' 'Rehearsal PostgreSQL volume is not isolated.'
require_text docker-compose.rehearsal.yml 'name: ims_merge_rehearsal_static_data' 'Rehearsal static volume is not isolated.'
require_text docker-compose.rehearsal.yml 'name: ims_merge_rehearsal_media_data' 'Rehearsal media volume is not isolated.'
require_text docker-compose.rehearsal.yml 'name: ims_merge_rehearsal_edge' 'Rehearsal edge network is not isolated.'
require_text docker-compose.rehearsal.yml 'name: ims_merge_rehearsal_database' 'Rehearsal database network is not isolated.'

if grep -Eq '^[[:space:]]+name: ims_(postgres_data|static_data|media_data|edge|database)[[:space:]]*$' docker-compose.rehearsal.yml; then
  fail 'Rehearsal override contains a production IMS resource identity.'
fi

require_text scripts/rehearse-production-freeze.sh 'merge_access_report --fail-on-errors' 'Rehearsal must validate company access.'
require_text scripts/rehearse-production-freeze.sh 'merge_inventory_tenant_report --fail-on-errors' 'Rehearsal must validate Inventory tenant boundaries.'
require_text scripts/rehearse-production-freeze.sh 'merge_shared_projects_report --fail-on-errors' 'Rehearsal must validate shared Projects.'
require_text scripts/rehearse-production-freeze.sh 'merge_internal_payroll_report --fail-on-errors' 'Rehearsal must validate Internal Payroll.'
require_text scripts/rehearse-production-freeze.sh 'merge_rental_manpower_report --fail-on-errors' 'Rehearsal must validate Rental Manpower.'
require_text scripts/rehearse-production-freeze.sh 'merge_documents_management_report --fail-on-errors' 'Rehearsal must validate Documents/Management.'
require_text scripts/rehearse-production-freeze.sh 'payroll_bootstrap_report --fail-on-errors' 'Rehearsal must render the production Payroll bootstrap.'
require_text scripts/rehearse-production-freeze.sh 'test --noinput' 'Rehearsal must run the full Django regression suite.'
require_text scripts/rehearse-production-freeze.sh 'compare-rehearsal-baselines.py' 'Rehearsal must enforce pre/post legacy IMS row-count preservation.'
require_text scripts/rehearse-production-freeze.sh 'rehearsal-data-fingerprint.py' 'Rehearsal must capture protected legacy IMS field fingerprints.'
require_text scripts/rehearse-production-freeze.sh 'compare-rehearsal-fingerprints.py' 'Rehearsal must reject legacy IMS field-data drift.'
rehearsal_collect_line="$(grep -nF 'run_manage collectstatic --noinput' scripts/rehearse-production-freeze.sh | head -1 | cut -d: -f1)"
rehearsal_bootstrap_line="$(grep -nF 'run_manage payroll_bootstrap_report --fail-on-errors' scripts/rehearse-production-freeze.sh | head -1 | cut -d: -f1)"
[[ -n "${rehearsal_collect_line}" && -n "${rehearsal_bootstrap_line}" ]] || fail 'Rehearsal static/bootstrap ordering cannot be verified.'
(( rehearsal_collect_line < rehearsal_bootstrap_line )) || fail 'Rehearsal must collect static assets before rendering Payroll templates.'
require_text scripts/deploy-production.sh 'scripts/verify-production-freeze.sh' 'Canonical production deployment must verify the packaged source freeze.'
require_text scripts/deploy-production-freeze.sh 'scripts/verify-production-freeze.sh' 'Compatibility deploy wrapper must verify the production freeze.'
require_text scripts/deploy-production-freeze.sh 'scripts/deploy-production.sh' 'Compatibility deploy wrapper must hand off to the canonical deployment pipeline.'

python3 - <<'PY'
import json
from pathlib import Path
p = Path('merge/source-manifest.json')
data = json.loads(p.read_text(encoding='utf-8'))
progress = data['merge_progress']
assert progress['completed_upgrade'] == 12
assert progress['total_upgrades'] == 12
assert progress['merge_complete'] is True
assert progress['next_upgrade'] is None
PY

printf 'Upgrade 12 production-freeze contract verified.\n'
