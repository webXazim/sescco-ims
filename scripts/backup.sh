#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command sha256sum

key_fingerprint="$(payroll_key_fingerprint)"
retention_days="${IMS_BACKUP_RETENTION_DAYS:-30}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
configured_backup_root="$(read_env_value IMS_BACKUP_DIR)"
backup_root="${IMS_BACKUP_DIR:-${configured_backup_root:-${PROJECT_ROOT}/backups}}"
if [[ "${backup_root}" != /* ]]; then
  backup_root="${PROJECT_ROOT}/${backup_root#./}"
fi
backup_dir="${backup_root}/${timestamp}"
mkdir -p "${backup_dir}"
chmod 700 "${backup_root}" "${backup_dir}"

info "Starting IMS database for backup"
compose up -d ims_db
wait_for_service_health ims_db 120

info "Creating PostgreSQL custom-format backup"
compose exec -T ims_db sh -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_dump --format=custom --compress=6 --no-owner --no-privileges \
    --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
' > "${backup_dir}/database.dump"
[[ -s "${backup_dir}/database.dump" ]] || fatal "Database backup is empty."

info "Creating private media backup"
compose run --rm --no-deps -T ims_tools sh -c \
  "tar -C /data/media -czf - ." > "${backup_dir}/media.tar.gz"

source_revision="$(git -C "${PROJECT_ROOT}" rev-parse HEAD 2>/dev/null || printf 'unknown')"
app_version="$(cat "${PROJECT_ROOT}/VERSION" 2>/dev/null || printf 'unknown')"
cat > "${backup_dir}/manifest.txt" <<MANIFEST
service=ims
platform=ims-payroll-merged
domain=ims.a2tdev.com
created_at_utc=${timestamp}
source_revision=${source_revision}
app_version=${app_version}
database_format=postgres_custom
media_format=tar_gzip
compose_project=ims
payroll_field_key_fingerprint_sha256=${key_fingerprint}
MANIFEST

(
  cd "${backup_dir}"
  sha256sum database.dump media.tar.gz manifest.txt > SHA256SUMS
)
chmod 600 "${backup_dir}"/*

if [[ "${retention_days}" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -mtime "+${retention_days}" \
    -print -exec rm -rf -- {} +
fi

printf '%s\n' "${backup_dir}"
