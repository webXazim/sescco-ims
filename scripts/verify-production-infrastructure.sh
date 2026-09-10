#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" pattern="$2" message="$3"
  grep -Fq -- "${pattern}" "${file}" || fail "${message}"
}

require_text docker-compose.yml 'name: ims' 'Compose project identity changed.'
require_text docker-compose.yml 'name: ims_postgres_data' 'PostgreSQL volume identity changed.'
require_text docker-compose.yml 'name: ims_static_data' 'Static volume identity changed.'
require_text docker-compose.yml 'name: ims_media_data' 'Media volume identity changed.'
require_text docker-compose.yml '127.0.0.1:${IMS_HTTP_PORT:-8087}:8080' 'Gateway must remain bound to loopback.'
require_text docker-compose.yml 'internal: true' 'Database network must remain internal.'
require_text docker-compose.yml 'RUN_STARTUP_TASKS: ${RUN_STARTUP_TASKS:-0}' 'Web startup must not auto-run migrations by default.'
require_text docker-compose.yml 'DB_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}' 'Django database password must derive from the canonical PostgreSQL password.'
require_text docker-compose.yml 'read_only: true' 'Web container root filesystem hardening is missing.'
require_text docker-compose.yml 'cap_drop:' 'Web capability drop is missing.'
require_text Dockerfile 'FROM python:3.13.15-slim-bookworm AS builder' 'Builder Python image is not pinned to the Upgrade 11 release base.'
require_text Dockerfile 'FROM python:3.13.15-slim-bookworm AS runtime' 'Runtime Python image is not pinned to the Upgrade 11 release base.'
require_text docker-compose.yml 'image: postgres:17.10-alpine3.23' 'PostgreSQL image identity changed.'
require_text docker-compose.yml 'image: nginx:1.30.4-alpine3.24' 'Gateway Nginx image identity changed.'
if grep -Eq '(^|[^0-9])5432:5432([^0-9]|$)' docker-compose.yml; then
  fail 'PostgreSQL must not be published to the host.'
fi

require_text scripts/deploy-production.sh 'scripts/release-tasks.sh' 'Deployment must run explicit release tasks.'
require_text scripts/create-production-env.sh 'secrets.token_urlsafe(64)' 'Production environment generator must create a strong Django secret.'
require_text scripts/create-production-env.sh 'secrets.token_bytes(32)' 'Production environment generator must create a valid Fernet key.'
require_text scripts/restore.sh 'scripts/release-tasks.sh' 'Restore must run current release tasks before web startup.'
require_text scripts/backup.sh 'payroll_field_key_fingerprint_sha256=' 'Backup must bind to the Payroll encryption key fingerprint.'
require_text scripts/restore.sh 'PAYROLL_FIELD_ENCRYPTION_KEY does not match' 'Restore must reject a mismatched Payroll encryption key.'
require_text scripts/restore.sh 'pg_restore --single-transaction' 'Database restore must be transactional.'
require_text scripts/release-tasks.sh 'merge_access_report --fail-on-errors' 'Release verification must check company access integrity.'
require_text scripts/release-tasks.sh 'merge_documents_management_report --fail-on-errors' 'Release verification must cover merged Payroll documents/management.'
require_text scripts/release-tasks.sh 'migrate --check' 'Release verification must finish with zero pending migrations.'
require_text scripts/release-tasks.sh 'collectstatic --noinput' 'Release tasks must collect static assets.'
if grep -Fq -- 'collectstatic --noinput --clear' scripts/release-tasks.sh scripts/deploy-production.sh scripts/entrypoint.sh; then
  fail 'Production rollout must not clear previous static assets during cutover.'
fi

require_text nginx/default.conf 'location /media/' 'Private media must have an explicit gateway rule.'
require_text nginx/default.conf 'return 404;' 'Private media must not be served directly by Nginx.'
require_text nginx/default.conf 'expires 1h;' 'Stable static compatibility URLs need bounded caching.'
require_text .env.production.example 'PAYROLL_FIELD_ENCRYPTION_KEY=' 'Production env example is missing Payroll field encryption key.'
require_text .env.production.example 'IMS_PUBLIC_DOMAIN=' 'Production env example is missing the public domain.'
require_text .env.production.example 'DJANGO_TRUSTED_PROXY_IPS=' 'Production env example is missing trusted proxy configuration.'
require_text .env.production.example 'DJANGO_TRUSTED_PROXY_IPS=127.0.0.1,::1,172.20.0.0/16' 'Production env example must trust the confirmed ims_edge subnet.'
require_text .env.production.example 'IMS_BACKUP_RETENTION_DAYS=' 'Production env example is missing backup retention configuration.'
require_text .env.production.example 'RUN_STARTUP_TASKS=0' 'Production runtime must explicitly disable startup migrations.'

[[ -f static/css/styles.css ]] || fail 'Inventory CSS entrypoint is missing.'
[[ -f static/platform/css/shell-switchers.css ]] || fail 'Shared platform shell CSS is missing.'
[[ -f static/payroll/css/v2/index.css ]] || fail 'Payroll V2 CSS entrypoint is missing.'
[[ -f static/payroll/js/app.js ]] || fail 'Payroll JS bundle is missing.'

sha256sum -c merge/production-infrastructure-assets.sha256 >/dev/null \
  || fail 'A frozen Upgrade 11 production-infrastructure asset changed.'

printf 'Production infrastructure contract verified.\n'
