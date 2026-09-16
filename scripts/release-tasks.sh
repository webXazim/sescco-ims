#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

seed_requested=0
seed_profile="${IMS_SEED_PROFILE:-functional}"
allow_mixed_scale_seed="${IMS_ALLOW_MIXED_SCALE_SEED:-0}"
while (( $# )); do
  case "$1" in
    --seed) seed_requested=1 ;;
    --seed-profile)
      shift
      [[ $# -gt 0 ]] || fatal "--seed-profile requires a value."
      seed_profile="$1"
      seed_requested=1
      ;;
    --seed-profile=*)
      seed_profile="${1#*=}"
      seed_requested=1
      ;;
    --allow-mixed-scale-seed)
      allow_mixed_scale_seed=1
      seed_requested=1
      ;;
    *) fatal "Unknown release-task option: $1" ;;
  esac
  shift
done
case "${seed_profile}" in
  functional|realistic|benchmark) ;;
  *) fatal "Unknown payroll seed profile: ${seed_profile}." ;;
esac

require_environment

info "Verifying final SESCCO MS release-candidate contract"
python3 "${PROJECT_ROOT}/scripts/verify-release-candidate.py"

info "Verifying granular access authority foundation"
python3 "${PROJECT_ROOT}/scripts/verify-granular-access-authority.py"
python3 "${PROJECT_ROOT}/scripts/verify-single-access-authority.py"
python3 "${PROJECT_ROOT}/scripts/verify-user-management-backend.py"
python3 "${PROJECT_ROOT}/scripts/verify-user-management-ui.py"
python3 "${PROJECT_ROOT}/scripts/verify-rental-supervisor-scope.py"
python3 "${PROJECT_ROOT}/scripts/verify-inventory-storekeeper-scope.py"
python3 "${PROJECT_ROOT}/scripts/verify-page-level-view-only.py"
python3 "${PROJECT_ROOT}/scripts/verify-internal-finance-permissions.py"
python3 "${PROJECT_ROOT}/scripts/verify-cross-module-access-leaks.py"
python3 "${PROJECT_ROOT}/scripts/verify-credential-session-revocation.py"
python3 "${PROJECT_ROOT}/scripts/verify-access-history-recovery.py"
python3 "${PROJECT_ROOT}/scripts/verify-index-name-hotfix.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-migration-state-hotfix.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-domain-foundation.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-access-control.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-vendor-master.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-material-catalog.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-material-finder.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-vendor-verification.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-manpower-master.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-trade-workforce-catalog.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-workforce-finder.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-data-exchange.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-scale-hardening.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-security-certification.py"
python3 "${PROJECT_ROOT}/scripts/verify-sourcing-browser-e2e.py"

info "Verifying frozen Payroll production-E2E certification contract"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-timesheet-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-bootstrap-search.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-query-hardening.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-browser-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-employee-residual-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-salary-setup-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-run-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-adjustment-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-assignment-project-selector-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-drawer-selector-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-rental-adjustment-selector-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-rental-adjustment-page-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-payment-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-shared-surfaces-scale.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-final-browser-certification.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-report-performance.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-document-finalization-context.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-document-production.py"
python3 "${PROJECT_ROOT}/scripts/verify-payroll-production-e2e.py"

run_manage() {
  compose run --rm --no-deps -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py "$@"
}

info "Running Django deployment checks against the release image"
run_manage check --deploy --fail-level ERROR
run_manage makemigrations --check --dry-run

info "Reviewing and applying database migrations"
run_manage migrate --plan
run_manage migrate --noinput
run_manage verify_company_settings_schema

if (( seed_requested )); then
  info "Seeding complete idempotent DEMO Payroll/WPS/report/lifecycle test data"
  seed_args=()
  if [[ -n "${IMS_SEED_COMPANY_SLUG:-}" ]]; then
    seed_args+=(--company-slug "${IMS_SEED_COMPANY_SLUG}")
  fi
  if [[ -n "${IMS_SEED_PERIOD:-}" ]]; then
    seed_args+=(--period "${IMS_SEED_PERIOD}")
  fi
  seed_args+=(--profile "${seed_profile}")
  if [[ "${allow_mixed_scale_seed}" == "1" ]]; then
    seed_args+=(--allow-mixed-scale-seed)
  fi
  if [[ -n "${IMS_SEED_BATCH_SIZE:-}" ]]; then
    seed_args+=(--seed-batch-size "${IMS_SEED_BATCH_SIZE}")
  fi
  run_manage seed_payroll_test_data "${seed_args[@]}"

  info "Seeding deterministic Sourcing reference fixtures for ${seed_profile} profile"
  sourcing_seed_args=(--profile "${seed_profile}")
  if [[ -n "${IMS_SEED_COMPANY_SLUG:-}" ]]; then
    sourcing_seed_args+=(--company-slug "${IMS_SEED_COMPANY_SLUG}")
  fi
  if [[ "${allow_mixed_scale_seed}" == "1" ]]; then
    sourcing_seed_args+=(--allow-mixed-scale-seed)
  fi
  if [[ -n "${IMS_SEED_BATCH_SIZE:-}" ]]; then
    sourcing_seed_args+=(--batch-size "${IMS_SEED_BATCH_SIZE}")
  fi
  run_manage seed_sourcing_test_data "${sourcing_seed_args[@]}"

  if [[ "${seed_profile}" == "benchmark" ]]; then
    info "Certifying benchmark-volume Sourcing directory/Finder performance"
    scale_args=(--require-benchmark-volume --fail-on-limits)
    if [[ -n "${IMS_SEED_COMPANY_SLUG:-}" ]]; then
      scale_args+=(--company-slug "${IMS_SEED_COMPANY_SLUG}")
    fi
    run_manage sourcing_scale_report "${scale_args[@]}"
  fi
fi

info "Verifying merged company/access boundaries"
run_manage merge_access_report --fail-on-errors >/dev/null
run_manage merge_inventory_tenant_report --fail-on-errors >/dev/null
run_manage merge_shared_projects_report --fail-on-errors >/dev/null
run_manage merge_internal_payroll_report --fail-on-errors >/dev/null
run_manage merge_rental_manpower_report --fail-on-errors >/dev/null
run_manage merge_documents_management_report --fail-on-errors >/dev/null
run_manage migrate --check

info "Running focused Sourcing domain/isolation regression"
run_manage test apps.sourcing.tests.test_domain_foundation --noinput
run_manage test apps.sourcing.tests.test_access_control --noinput
run_manage test apps.sourcing.tests.test_vendor_master --noinput
run_manage test apps.sourcing.tests.test_material_catalog --noinput
run_manage test apps.sourcing.tests.test_material_finder --noinput
run_manage test apps.sourcing.tests.test_vendor_verification --noinput
run_manage test apps.sourcing.tests.test_manpower_master --noinput
run_manage test apps.sourcing.tests.test_trade_workforce_catalog --noinput
run_manage test apps.sourcing.tests.test_workforce_finder --noinput
run_manage test apps.sourcing.tests.test_data_exchange --noinput
run_manage test apps.sourcing.tests.test_scale_hardening --noinput
run_manage test apps.sourcing.tests.test_security_certification --noinput
run_manage test apps.sourcing.tests.test_browser_e2e_freeze --noinput

info "Collecting static assets without deleting the previous release assets"
run_manage collectstatic --noinput

info "Rendering the production Payroll bootstrap before live cutover"
run_manage payroll_bootstrap_report --fail-on-errors

info "Release tasks completed"
