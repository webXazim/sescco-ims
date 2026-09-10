#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command sha256sum
require_command git

info "Verifying deployment repository state"
git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || fatal "Production deployment must run from the packaged Git working tree."
[[ -z "$(git -C "${PROJECT_ROOT}" status --porcelain --untracked-files=normal)" ]] \
  || fatal "Production deployment requires a clean Git working tree. Commit or remove local source changes first."

info "Verifying immutable merge baseline"
bash "${PROJECT_ROOT}/scripts/verify-merge-baseline.sh"

info "Verifying merged Payroll frontend"
bash "${PROJECT_ROOT}/scripts/verify-payroll-frontend.sh"

info "Verifying unified platform shell"
bash "${PROJECT_ROOT}/scripts/verify-platform-shell.sh"

info "Verifying merged production infrastructure"
bash "${PROJECT_ROOT}/scripts/verify-production-infrastructure.sh"

info "Validating production environment"
required=(
  DJANGO_SECRET_KEY
  PAYROLL_FIELD_ENCRYPTION_KEY
  DJANGO_ALLOWED_HOSTS
  DJANGO_CSRF_TRUSTED_ORIGINS
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
)
for key in "${required[@]}"; do
  value="$(read_env_value "${key}")"
  [[ -n "${value}" ]] || fatal "${key} is missing from ${ENV_FILE}"
done

secret="$(read_env_value DJANGO_SECRET_KEY)"
[[ ${#secret} -ge 50 ]] || fatal "DJANGO_SECRET_KEY must contain at least 50 characters."

field_key="$(read_env_value PAYROLL_FIELD_ENCRYPTION_KEY)"
[[ ${#field_key} -eq 44 && "${field_key}" =~ ^[A-Za-z0-9_-]{43}=$ ]] \
  || fatal "PAYROLL_FIELD_ENCRYPTION_KEY must be a valid 44-character Fernet key."

password="$(read_env_value POSTGRES_PASSWORD)"
[[ ${#password} -ge 20 ]] || fatal "POSTGRES_PASSWORD must contain at least 20 characters."

allowed_hosts="$(read_env_value DJANGO_ALLOWED_HOSTS)"
csrf_origins="$(read_env_value DJANGO_CSRF_TRUSTED_ORIGINS)"
[[ ",${allowed_hosts}," == *",ims.a2tdev.com,"* ]] \
  || fatal "DJANGO_ALLOWED_HOSTS must include ims.a2tdev.com."
[[ ",${csrf_origins}," == *",https://ims.a2tdev.com,"* ]] \
  || fatal "DJANGO_CSRF_TRUSTED_ORIGINS must include https://ims.a2tdev.com."

if grep -Eq 'replace-with|development-only|changeme|example-password' "${ENV_FILE}"; then
  fatal "Placeholder secrets remain in ${ENV_FILE}."
fi

permissions="$(stat -c '%a' "${ENV_FILE}" 2>/dev/null || stat -f '%Lp' "${ENV_FILE}")"
if [[ "${permissions}" != "600" && "${permissions}" != "640" ]]; then
  printf 'WARNING: Set restrictive permissions with: chmod 600 %q\n' "${ENV_FILE}" >&2
fi

trusted_proxies="$(read_env_value DJANGO_TRUSTED_PROXY_IPS)"
[[ -n "${trusted_proxies}" ]] \
  || fatal "DJANGO_TRUSTED_PROXY_IPS must explicitly identify the Docker gateway/proxy network in production."

app_uid="$(read_env_value IMS_APP_UID)"
app_gid="$(read_env_value IMS_APP_GID)"
app_uid="${app_uid:-10001}"
app_gid="${app_gid:-10001}"
[[ "${app_uid}" =~ ^[0-9]+$ && "${app_gid}" =~ ^[0-9]+$ ]] \
  || fatal "IMS_APP_UID and IMS_APP_GID must be numeric."

if [[ "${shared_proxy_setting:-0}" == "1" ]]; then
  proxy_network="$(read_env_value IMS_PROXY_NETWORK)"
  [[ -n "${proxy_network}" ]] || fatal "IMS_PROXY_NETWORK is required for shared proxy mode."
  docker network inspect "${proxy_network}" >/dev/null 2>&1 \
    || fatal "Shared proxy network does not exist: ${proxy_network}"
fi

info "Validating Compose configuration"
compose config --quiet

info "Preflight passed"
