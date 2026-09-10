#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command curl
lock_dir="${PROJECT_ROOT}/.deploy-lock"
mkdir "${lock_dir}" 2>/dev/null || fatal "Another IMS deployment appears to be running."
trap 'rmdir "${lock_dir}" 2>/dev/null || true' EXIT

info "Verifying the packaged production source freeze"
bash "${PROJECT_ROOT}/scripts/verify-production-freeze.sh"

bash "${PROJECT_ROOT}/scripts/preflight.sh"

info "Building the merged IMS + Payroll release image"
compose build --pull ims_web

info "Starting the isolated IMS database"
compose up -d ims_db
wait_for_service_health ims_db 120

if [[ "${IMS_SKIP_DEPLOY_BACKUP:-0}" != "1" ]]; then
  info "Creating a pre-deployment database/media backup"
  bash "${PROJECT_ROOT}/scripts/backup.sh" >/dev/null
fi

# Run all schema/static/integrity work against the newly built image while the
# currently running web/gateway containers remain available. Merge migrations
# follow the documented expand/backfill/constrain policy and remain compatible
# with the previous release during this short cutover window.
info "Preparing the release before replacing the web container"
bash "${PROJECT_ROOT}/scripts/release-tasks.sh"

info "Starting or updating the merged web service"
compose up -d ims_web
wait_for_service_health ims_web 300

info "Starting or updating the IMS gateway"
compose up -d ims_gateway
wait_for_service_health ims_gateway 120
info "Validating and reloading the gateway configuration"
compose exec -T ims_gateway nginx -t
compose exec -T ims_gateway nginx -s reload
wait_for_service_health ims_gateway 60

info "Running final Django deployment checks inside the live container"
compose exec -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py check --deploy --fail-level ERROR
compose exec -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py makemigrations --check --dry-run

http_port="$(read_env_value IMS_HTTP_PORT)"
http_port="${http_port:-8087}"
public_domain="$(read_env_value IMS_PUBLIC_DOMAIN)"
info "Running local gateway readiness smoke test"
curl --fail --silent --show-error \
  --header "Host: ${public_domain}" \
  --header 'X-Forwarded-Proto: https' \
  "http://127.0.0.1:${http_port}/app/health/ready/" >/dev/null

info "Verifying Inventory and Payroll static assets through the gateway"
for asset in \
  /static/css/styles.css \
  /static/platform/css/shell-switchers.css \
  /static/platform/css/inventory-shell.css \
  /static/platform/css/payroll-shell-fixes.css \
  /static/platform/js/inventory-shell.js \
  /static/payroll/css/v2/index.css \
  /static/payroll/js/app.js; do
  curl --fail --silent --show-error \
    --header "Host: ${public_domain}" \
    --header 'X-Forwarded-Proto: https' \
    "http://127.0.0.1:${http_port}${asset}" >/dev/null
done

info "Deployment completed"
printf 'Local origin: http://127.0.0.1:%s\n' "${http_port}"
printf 'Public domain: https://%s\n' "${public_domain}"
printf 'Compose project and persistent volume identities were preserved.\n'
