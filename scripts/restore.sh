#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/restore.sh /absolute/or/project-relative/backup-directory --confirm

This replaces the IMS PostgreSQL database and private media volume. It never
operates on another Compose project, but it is destructive to current IMS data.
USAGE
}

[[ $# -ge 2 ]] || { usage; exit 2; }
backup_dir="$1"
confirmation="$2"
[[ "${confirmation}" == "--confirm" ]] || fatal "Pass --confirm to acknowledge replacement."

require_environment
require_command sha256sum
if [[ "${backup_dir}" != /* ]]; then
  backup_dir="${PROJECT_ROOT}/${backup_dir#./}"
fi
[[ -d "${backup_dir}" ]] || fatal "Backup directory not found: ${backup_dir}"
[[ -s "${backup_dir}/database.dump" ]] || fatal "database.dump is missing or empty."
[[ -f "${backup_dir}/media.tar.gz" ]] || fatal "media.tar.gz is missing."
[[ -f "${backup_dir}/manifest.txt" ]] || fatal "manifest.txt is missing."
[[ -f "${backup_dir}/SHA256SUMS" ]] || fatal "SHA256SUMS is missing."

info "Verifying backup checksums"
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)

manifest_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${backup_dir}/manifest.txt"
}

[[ "$(manifest_value service)" == "ims" ]] || fatal "Backup manifest is not an IMS backup."
[[ "$(manifest_value compose_project)" == "ims" ]] || fatal "Backup manifest Compose project does not match ims."
backup_platform="$(manifest_value platform)"
if [[ -n "${backup_platform}" && "${backup_platform}" != "ims-payroll-merged" ]]; then
  fatal "Backup manifest platform does not match the merged IMS + Payroll platform."
fi
backup_key_fingerprint="$(manifest_value payroll_field_key_fingerprint_sha256)"
current_key_fingerprint="$(payroll_key_fingerprint)"
if [[ -z "${backup_key_fingerprint}" ]]; then
  [[ "${IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT:-0}" == "1" ]] \
    || fatal "Backup predates encryption-key binding. Set IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT=1 only after confirming it contains no encrypted Payroll data."
  printf 'WARNING: Restoring a legacy backup without a Payroll encryption-key fingerprint.\n' >&2
elif [[ "${backup_key_fingerprint}" != "${current_key_fingerprint}" ]]; then
  fatal "PAYROLL_FIELD_ENCRYPTION_KEY does not match the key used by this backup. Restore is blocked to protect encrypted payroll data."
fi

info "Building the current release image before destructive restore steps"
compose build ims_web
compose up -d ims_db
wait_for_service_health ims_db 120

info "Validating database and media backup archives before replacement"
compose exec -T ims_db pg_restore --list < "${backup_dir}/database.dump" >/dev/null \
  || fatal "database.dump is not a readable PostgreSQL custom-format archive."
configured_backup_root="$(read_env_value IMS_BACKUP_DIR)"
backup_root="${IMS_BACKUP_DIR:-${configured_backup_root:-${PROJECT_ROOT}/backups}}"
if [[ "${backup_root}" != /* ]]; then
  backup_root="${PROJECT_ROOT}/${backup_root#./}"
fi
relative_backup="${backup_dir#${backup_root}/}"
[[ "${relative_backup}" != "${backup_dir}" ]] \
  || fatal "Backup must be located inside ${backup_root} for media restoration."
compose run --rm --no-deps -T -e BACKUP_SUBDIR="${relative_backup}" ims_tools sh -c \
  'tar -tzf "/backups/${BACKUP_SUBDIR}/media.tar.gz" >/dev/null' \
  || fatal "media.tar.gz is not a readable gzip/tar archive."
if compose run --rm --no-deps -T -e BACKUP_SUBDIR="${relative_backup}" ims_tools sh -c \
  'tar -tzf "/backups/${BACKUP_SUBDIR}/media.tar.gz" | grep -Eq "(^/|(^|/)\.\.(/|$))"'; then
  fatal "media.tar.gz contains an unsafe path."
fi

if [[ "${IMS_SKIP_SAFETY_BACKUP:-0}" != "1" ]]; then
  info "Creating safety backup of the current IMS data"
  IMS_BACKUP_RETENTION_DAYS=0 bash "${PROJECT_ROOT}/scripts/backup.sh" >/dev/null
fi

info "Stopping only IMS application services"
compose stop ims_gateway ims_web || true
compose up -d ims_db
wait_for_service_health ims_db 120

postgres_db="$(read_env_value POSTGRES_DB)"
postgres_user="$(read_env_value POSTGRES_USER)"
[[ "${postgres_db}" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || fatal "Unsafe POSTGRES_DB value."
[[ "${postgres_user}" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || fatal "Unsafe POSTGRES_USER value."

info "Replacing the IMS database"
compose exec -T ims_db sh -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  dropdb --if-exists --force --username="$POSTGRES_USER" "$POSTGRES_DB"
  createdb --username="$POSTGRES_USER" --owner="$POSTGRES_USER" "$POSTGRES_DB"
'

compose exec -T ims_db sh -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_restore --single-transaction --exit-on-error --no-owner --no-privileges \
    --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
' < "${backup_dir}/database.dump"

info "Replacing the IMS private media volume"
compose run --rm --no-deps -T -e BACKUP_SUBDIR="${relative_backup}" ims_tools sh -c \
  'rm -rf /data/media/* /data/media/.[!.]* /data/media/..?* 2>/dev/null || true; tar -C /data/media -xzf "/backups/${BACKUP_SUBDIR}/media.tar.gz"'

info "Applying current release migrations, integrity checks and static assets"
bash "${PROJECT_ROOT}/scripts/release-tasks.sh"

info "Starting IMS application services"
compose up -d ims_web
wait_for_service_health ims_web 240
compose up -d ims_gateway
wait_for_service_health ims_gateway 120

info "Restore completed"
