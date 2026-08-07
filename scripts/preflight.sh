#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment

info "Validating production environment"
required=(
  DJANGO_SECRET_KEY
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

if [[ "${shared_proxy_setting:-0}" == "1" ]]; then
  proxy_network="$(read_env_value IMS_PROXY_NETWORK)"
  [[ -n "${proxy_network}" ]] || fatal "IMS_PROXY_NETWORK is required for shared proxy mode."
  docker network inspect "${proxy_network}" >/dev/null 2>&1 \
    || fatal "Shared proxy network does not exist: ${proxy_network}"
fi

info "Validating Compose configuration"
compose config --quiet

info "Preflight passed"
