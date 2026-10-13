#!/usr/bin/env bash
# Change the existing IMS hostname without rebuilding or running release tasks.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN=ms.sescco.com
EXPECTED_IP=31.70.114.86
EMAIL=
case "${1:-}" in
  --email) EMAIL="${2:?Supply the certificate contact email}"; shift 2 ;;
  -h|--help)
    printf 'Usage: sudo bash scripts/change-public-domain.sh [--email ADDRESS]\n'
    exit 0 ;;
esac
[[ $# -eq 0 ]] || { printf 'Unknown arguments. Use --help.\n' >&2; exit 2; }
if [[ ${EUID} -ne 0 ]]; then
  args=()
  [[ -z "${EMAIL}" ]] || args=(--email "${EMAIL}")
  exec sudo bash "$0" "${args[@]}"
fi
cd "${ROOT}"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command in docker nginx certbot curl python3 openssl getent systemctl; do
  command -v "${command}" >/dev/null || fail "Install the missing prerequisite: ${command}"
done
[[ -f .env.production && -f docker-compose.yml ]] || fail 'Run this from the existing /opt/sites/ims checkout with its production environment.'
for suffix in bootstrap.conf conf; do
  [[ -f "deploy/host-nginx/${DOMAIN}.${suffix}" ]] || fail "Missing deploy/host-nginx/${DOMAIN}.${suffix} from the cutover package."
done
export IMS_ENV_FILE="${ROOT}/.env.production"
dc() { docker compose --env-file "${IMS_ENV_FILE}" -f "${ROOT}/docker-compose.yml" "$@"; }
read_value() {
  python3 - "$IMS_ENV_FILE" "$1" <<'PY'
import sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
    key, sep, value = line.partition('=')
    if sep and key.strip() == sys.argv[2]:
        print(value.strip().strip('\"\''))
        break
PY
}
[[ "$(read_value IMS_USE_SHARED_PROXY)" != 1 ]] || fail 'This script requires host Nginx, rather than a Docker shared proxy.'
[[ "$(read_value IMS_HTTP_PORT)" == 8087 ]] || fail 'The existing IMS gateway must use loopback port 8087.'
startup_tasks="$(read_value RUN_STARTUP_TASKS)"
[[ "${startup_tasks:-0}" == 0 ]] || fail 'Set RUN_STARTUP_TASKS=0 before a hostname-only restart.'
# An omitted value defaults to zero in Compose. Pin the effective value as well
# so an inherited shell variable cannot enable release tasks during recreation.
export RUN_STARTUP_TASKS=0
[[ "$(read_value COMPOSE_PROJECT_NAME)" == ims ]] || fail 'The existing Compose project must be ims.'
dc config --quiet
for service in ims_db ims_web ims_gateway; do
  cid="$(dc ps -q "${service}")"
  [[ -n "${cid}" ]] || fail "${service} is not running. Deploy IMS before changing its hostname."
  [[ "$(docker inspect --format '{{.State.Running}}' "${cid}")" == true ]] || fail "${service} is stopped."
done
nginx -t
systemctl is-active --quiet nginx || fail 'Host Nginx must already be running.'
getent ahostsv4 "${DOMAIN}" | awk '{print $1}' | sort -u | grep -Fxq "${EXPECTED_IP}" \
  || fail "${DOMAIN} must resolve directly to ${EXPECTED_IP} during certificate setup."
curl --fail --silent --show-error --max-time 30 https://sescco.com/ -o /dev/null

SITE_AVAILABLE="/etc/nginx/sites-available/${DOMAIN}"
SITE_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
[[ ! -L "${SITE_AVAILABLE}" ]] || fail "${SITE_AVAILABLE} is a symlink; inspect its target before changing it."
# Refuse a second explicit virtual host for this name. Unknown-host default
# routing is replaced by the new explicit virtual host normally.
nginx -T 2>&1 | python3 -c '
import re, sys
current = ""
allowed = {"/etc/nginx/sites-available/ms.sescco.com", "/etc/nginx/sites-enabled/ms.sescco.com"}
for line in sys.stdin:
    match = re.match(r"# configuration file (.+):", line)
    if match:
        current = match.group(1)
    match = re.search(r"\bserver_name\s+([^;]+);", line.split("#", 1)[0])
    if match and "ms.sescco.com" in match.group(1).split() and current not in allowed:
        sys.exit("ERROR: ms.sescco.com is already configured in " + current + "; reconcile that virtual host first.")
'

CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
KEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
NEED_CERT=1
if [[ -f "${CERT}" && -f "${KEY}" ]] \
  && openssl x509 -in "${CERT}" -noout -checkhost "${DOMAIN}" >/dev/null 2>&1 \
  && openssl x509 -in "${CERT}" -noout -checkend 604800 >/dev/null 2>&1; then
  NEED_CERT=0
fi
if [[ "${NEED_CERT}" == 1 && -z "${EMAIL}" ]]; then
  read -r -p 'Email for the HTTPS certificate renewal contact: ' EMAIL
fi
if [[ "${NEED_CERT}" == 1 ]]; then
  [[ "${EMAIL}" == *@*.* && "${EMAIL}" != -* && "${EMAIL}" != *' '* ]] || fail 'A valid certificate contact email is required.'
fi

umask 077
install -d -m 700 "${ROOT}/backups"
BACKUP_DIR="$(mktemp -d "${ROOT}/backups/domain-${DOMAIN}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
cp -a .env.production "${BACKUP_DIR}/environment"
[[ ! -e "${SITE_AVAILABLE}" ]] || cp -a "${SITE_AVAILABLE}" "${BACKUP_DIR}/nginx-available"
if [[ -e "${SITE_ENABLED}" || -L "${SITE_ENABLED}" ]]; then
  cp -a "${SITE_ENABLED}" "${BACKUP_DIR}/nginx-enabled"
fi
# Save an executable recovery command before making the first change.
cat > "${BACKUP_DIR}/rollback.sh" <<'ROLLBACK'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run rollback with sudo bash.' >&2; exit 1; }
BACKUP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "${BACKUP}")")"
cp -a "${BACKUP}/environment" "${ROOT}/.env.production"
for kind in available enabled; do
  target="/etc/nginx/sites-${kind}/ms.sescco.com"
  rm -f -- "${target}"
  if [[ -e "${BACKUP}/nginx-${kind}" || -L "${BACKUP}/nginx-${kind}" ]]; then
    cp -a "${BACKUP}/nginx-${kind}" "${target}"
  fi
done
export IMS_ENV_FILE="${ROOT}/.env.production"
export RUN_STARTUP_TASKS=0
dc() { docker compose --env-file "${IMS_ENV_FILE}" -f "${ROOT}/docker-compose.yml" "$@"; }
dc up -d --no-build --no-deps --pull never --force-recreate --wait --wait-timeout 180 ims_web
dc exec -T ims_gateway nginx -t
dc exec -T ims_gateway nginx -s reload
nginx -t
systemctl reload nginx
echo 'Previous IMS domain settings and virtual host restored.'
ROLLBACK
CHANGED=0
rollback_on_error() {
  code=$?
  trap - ERR INT TERM
  if [[ "${CHANGED}" == 1 ]]; then
    printf '\nCutover failed; restoring the saved configuration.\n' >&2
    if ! bash "${BACKUP_DIR}/rollback.sh"; then
      printf 'Automatic rollback needs attention. Run: sudo bash %q\n' "${BACKUP_DIR}/rollback.sh" >&2
    fi
  fi
  printf 'Recovery files: %s\n' "${BACKUP_DIR}" >&2
  exit "${code}"
}
trap rollback_on_error ERR
trap 'false' INT TERM
CHANGED=1
install -d -m 755 /var/www/certbot
install -m 644 "deploy/host-nginx/${DOMAIN}.bootstrap.conf" "${SITE_AVAILABLE}"
ln -sfn "${SITE_AVAILABLE}" "${SITE_ENABLED}"
nginx -t
systemctl reload nginx
if [[ "${NEED_CERT}" == 1 ]]; then
  certbot certonly --webroot -w /var/www/certbot --cert-name "${DOMAIN}" \
    -d "${DOMAIN}" --non-interactive --agree-tos --email "${EMAIL}"
fi
install -m 644 "deploy/host-nginx/${DOMAIN}.conf" "${SITE_AVAILABLE}"
nginx -t
systemctl reload nginx

python3 - "${IMS_ENV_FILE}" <<'PY'
import os
import re
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
original = path.read_text()
updates = {
    'IMS_PUBLIC_DOMAIN': 'ms.sescco.com',
    'DJANGO_ALLOWED_HOSTS': 'ms.sescco.com,localhost,127.0.0.1',
    'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://ms.sescco.com',
}
text = original
for key, value in updates.items():
    pattern = rf'(?m)^[ \t]*{key}[ \t]*=.*$'
    if len(re.findall(pattern, original)) != 1:
        raise SystemExit(f'Expected exactly one {key} entry; environment left unchanged.')
    text = re.sub(pattern, f'{key}={value}', text)
stat = path.stat()
fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.domain-env-')
try:
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    os.chmod(temporary, stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
print('Updated only the IMS domain, allowed hosts, and CSRF origins.')
PY
dc config --quiet
dc up -d --no-build --no-deps --pull never --force-recreate --wait --wait-timeout 180 ims_web
# Nginx resolves its upstream at reload; the recreated web container may have a new IP.
dc exec -T ims_gateway nginx -t
dc exec -T ims_gateway nginx -s reload
curl --fail --silent --show-error --retry 5 --retry-delay 2 --retry-all-errors \
  --max-time 20 -H "Host: ${DOMAIN}" -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8087/app/health/ready/
printf '\n'
curl --fail --silent --show-error --max-time 30 "https://${DOMAIN}/app/health/ready/"
printf '\n'
curl --fail --silent --show-error --max-time 30 "https://${DOMAIN}/login/" -o /dev/null
curl --fail --silent --show-error --max-time 30 "https://${DOMAIN}/static/platform/brand-sescco-mark.webp" -o /dev/null
curl --fail --silent --show-error --max-time 30 https://sescco.com/ -o /dev/null
nginx -t
trap - ERR INT TERM
printf '\nReady: https://%s/login/\nCompany site verified: https://sescco.com/\n' "${DOMAIN}"
printf 'Backup: %s\nRollback: sudo bash %q\n' "${BACKUP_DIR}" "${BACKUP_DIR}/rollback.sh"
