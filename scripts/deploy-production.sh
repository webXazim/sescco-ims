#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command curl
lock_dir="${PROJECT_ROOT}/.deploy-lock"
mkdir "${lock_dir}" 2>/dev/null || fatal "Another IMS deployment appears to be running."
trap 'rmdir "${lock_dir}" 2>/dev/null || true' EXIT

"${PROJECT_ROOT}/scripts/preflight.sh"

info "Building the IMS image without touching other Docker projects"
compose build --pull ims_web

info "Starting the isolated IMS database"
compose up -d ims_db
wait_for_service_health ims_db 120

if [[ "${IMS_SKIP_DEPLOY_BACKUP:-0}" != "1" ]]; then
  info "Creating a pre-deployment backup"
  "${PROJECT_ROOT}/scripts/backup.sh" >/dev/null
fi

info "Starting or updating IMS services"
compose up -d --remove-orphans ims_db ims_web ims_gateway
wait_for_service_health ims_web 300
wait_for_service_health ims_gateway 120

info "Running final Django deployment checks"
compose exec -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py check --deploy --fail-level ERROR
compose exec -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py makemigrations --check --dry-run

http_port="$(read_env_value IMS_HTTP_PORT)"
http_port="${http_port:-8087}"
info "Running local gateway smoke test"
curl --fail --silent --show-error \
  --header 'Host: ims.a2tdev.com' \
  --header 'X-Forwarded-Proto: https' \
  "http://127.0.0.1:${http_port}/app/health/ready/" >/dev/null

info "Deployment completed"
printf 'Local origin: http://127.0.0.1:%s\n' "${http_port}"
printf 'Public domain: https://ims.a2tdev.com\n'
printf 'This script did not stop, prune, or recreate any other Docker project.\n'
