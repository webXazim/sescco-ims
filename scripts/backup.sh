#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command sha256sum
require_command git
require_command tar

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
[[ -s "${backup_dir}/media.tar.gz" ]] || fatal "Private media backup is empty."

source_revision="$(git -C "${PROJECT_ROOT}" rev-parse HEAD 2>/dev/null || printf 'unknown')"
source_worktree_state="clean"
if ! git -C "${PROJECT_ROOT}" diff --quiet HEAD --; then
  source_worktree_state="dirty"
fi

info "Creating recoverable source-code bundle"
git -C "${PROJECT_ROOT}" bundle create "${backup_dir}/source.bundle" --all
[[ -s "${backup_dir}/source.bundle" ]] || fatal "Source-code bundle is empty."
if [[ "${source_worktree_state}" == "dirty" ]]; then
  git -C "${PROJECT_ROOT}" diff --binary HEAD -- > "${backup_dir}/source-working-tree.patch"
fi

info "Creating encrypted recovery configuration bundle"
[[ -f "${ENV_FILE}" ]] || fatal "Production environment file is missing."
tar -C "$(dirname "${ENV_FILE}")" -czf "${backup_dir}/production-config.tar.gz" "$(basename "${ENV_FILE}")"
[[ -s "${backup_dir}/production-config.tar.gz" ]] || fatal "Production configuration bundle is empty."

app_version="$(cat "${PROJECT_ROOT}/VERSION" 2>/dev/null || printf 'unknown')"
public_domain="$(read_env_value IMS_PUBLIC_DOMAIN)"
cat > "${backup_dir}/manifest.txt" <<MANIFEST
service=ims
platform=ims-payroll-merged
domain=${public_domain}
created_at_utc=${timestamp}
source_revision=${source_revision}
source_worktree_state=${source_worktree_state}
app_version=${app_version}
database_format=postgres_custom
media_format=tar_gzip
source_format=git_bundle
production_config_format=tar_gzip
compose_project=ims
payroll_field_key_fingerprint_sha256=${key_fingerprint}
MANIFEST

(
  cd "${backup_dir}"
  sha256sum database.dump media.tar.gz source.bundle production-config.tar.gz manifest.txt > SHA256SUMS
  if [[ -f source-working-tree.patch ]]; then
    sha256sum source-working-tree.patch >> SHA256SUMS
  fi
)
chmod 600 "${backup_dir}"/*

if [[ "${retention_days}" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  find "${backup_root}" -mindepth 1 -maxdepth 1 -type d -mtime "+${retention_days}" \
    -print -exec rm -rf -- {} +
fi

printf '%s\n' "${backup_dir}"
