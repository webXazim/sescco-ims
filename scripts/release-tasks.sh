#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

seed_requested=0
seed_profile="${IMS_SEED_PROFILE:-functional}"
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

info "Verifying frozen Payroll production-E2E certification contract"
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
  if [[ -n "${IMS_SEED_BATCH_SIZE:-}" ]]; then
    seed_args+=(--seed-batch-size "${IMS_SEED_BATCH_SIZE}")
  fi
  run_manage seed_payroll_test_data "${seed_args[@]}"
fi

info "Verifying merged company/access boundaries"
run_manage merge_access_report --fail-on-errors >/dev/null
run_manage merge_inventory_tenant_report --fail-on-errors >/dev/null
run_manage merge_shared_projects_report --fail-on-errors >/dev/null
run_manage merge_internal_payroll_report --fail-on-errors >/dev/null
run_manage merge_rental_manpower_report --fail-on-errors >/dev/null
run_manage merge_documents_management_report --fail-on-errors >/dev/null
run_manage migrate --check

info "Collecting static assets without deleting the previous release assets"
run_manage collectstatic --noinput

info "Rendering the production Payroll bootstrap before live cutover"
run_manage payroll_bootstrap_report --fail-on-errors

info "Release tasks completed"
