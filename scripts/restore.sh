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
if [[ "${backup_dir}" != /* ]]; then
  backup_dir="${PROJECT_ROOT}/${backup_dir#./}"
fi
[[ -d "${backup_dir}" ]] || fatal "Backup directory not found: ${backup_dir}"
[[ -s "${backup_dir}/database.dump" ]] || fatal "database.dump is missing or empty."
[[ -f "${backup_dir}/media.tar.gz" ]] || fatal "media.tar.gz is missing."

info "Verifying backup checksums"
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)

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
  pg_restore --exit-on-error --no-owner --no-privileges \
    --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
' < "${backup_dir}/database.dump"

info "Replacing the IMS private media volume"
configured_backup_root="$(read_env_value IMS_BACKUP_DIR)"
backup_root="${IMS_BACKUP_DIR:-${configured_backup_root:-${PROJECT_ROOT}/backups}}"
if [[ "${backup_root}" != /* ]]; then
  backup_root="${PROJECT_ROOT}/${backup_root#./}"
fi
relative_backup="${backup_dir#${backup_root}/}"
[[ "${relative_backup}" != "${backup_dir}" ]] \
  || fatal "Backup must be located inside ${backup_root} for media restoration."
compose run --rm --no-deps -T -e BACKUP_SUBDIR="${relative_backup}" ims_tools sh -c \
  'rm -rf /data/media/* /data/media/.[!.]* /data/media/..?* 2>/dev/null || true; tar -C /data/media -xzf "/backups/${BACKUP_SUBDIR}/media.tar.gz"'

info "Starting IMS and applying current migrations"
compose up -d ims_web ims_gateway
wait_for_service_health ims_web 240
wait_for_service_health ims_gateway 120

info "Restore completed"
