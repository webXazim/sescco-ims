#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT}/.env.production.example"
TARGET="${1:-${ROOT}/.env.production}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "${PYTHON_BIN}" >/dev/null 2>&1 \
  || fail "${PYTHON_BIN} is required to generate secrets."
[[ -f "${TEMPLATE}" ]] || fail "Template not found: ${TEMPLATE}"
[[ ! -e "${TARGET}" ]] || fail "Refusing to overwrite existing file: ${TARGET}"

mapfile -t generated < <("${PYTHON_BIN}" - <<'PY'
import base64
import secrets

print(secrets.token_urlsafe(64))
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"))
print(secrets.token_urlsafe(48))
PY
)

[[ ${#generated[@]} -eq 3 ]] || fail "Secret generation failed."
umask 077
sed \
  -e "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${generated[0]}|" \
  -e "s|^PAYROLL_FIELD_ENCRYPTION_KEY=.*|PAYROLL_FIELD_ENCRYPTION_KEY=${generated[1]}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${generated[2]}|" \
  "${TEMPLATE}" > "${TARGET}"
chmod 600 "${TARGET}"

printf 'Created %s with generated Django, Payroll, and PostgreSQL secrets.\n' "${TARGET}"
printf 'Review SMTP settings and shared-proxy settings before deployment.\n'
