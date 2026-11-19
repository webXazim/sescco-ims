#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"
source "${PROJECT_ROOT}/scripts/lib/backup.sh"

require_environment
require_command sha256sum
require_command git
require_command tar
require_command flock

key_fingerprint="$(payroll_key_fingerprint)"
retention_days="$(backup_setting IMS_BACKUP_RETENTION_DAYS 7)"
keep_count="$(backup_setting IMS_BACKUP_KEEP_COUNT 7)"
quiesce_web="$(backup_setting IMS_BACKUP_QUIESCE_WEB 0)"
[[ "${quiesce_web}" == 0 || "${quiesce_web}" == 1 ]] || fatal "IMS_BACKUP_QUIESCE_WEB must be 0 or 1."
[[ "${retention_days}" =~ ^(0|[1-9][0-9]*)$ && "${keep_count}" =~ ^[1-9][0-9]*$ ]] \
  || fatal "Backup retention must be non-negative days and a positive keep count."
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_root="$(backup_root_path)"
exec 9>"${backup_root}/.backup.lock"
flock -n 9 || fatal "Another local backup is running."
final_backup_dir="${backup_root}/${timestamp}"
[[ ! -e "${final_backup_dir}" ]] || fatal "Backup timestamp already exists. Retry in one second."
backup_dir="$(mktemp -d "${backup_root}/.partial-${timestamp}.XXXXXX")"
web_stopped=0
resume_web() {
  if (( web_stopped )); then
    info "Resuming IMS web after backup capture"
    compose start ims_web
    wait_for_service_health ims_web 240
    web_stopped=0
  fi
}
cleanup() {
  local status=$?
  # Recovery also runs when dumping/archiving fails or systemd sends SIGTERM.
  resume_web || status=1
  [[ -z "${backup_dir:-}" ]] || rm -rf -- "${backup_dir}"
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
chmod 700 "${backup_root}" "${backup_dir}"

info "Starting IMS database for backup"
compose up -d ims_db
wait_for_service_health ims_db 120

if [[ "${quiesce_web}" == 1 ]]; then
  running_services="$(compose ps --status running --services)"
  if grep -qx ims_web <<< "${running_services}"; then
    info "Briefly stopping IMS writers for consistent database and document capture"
    web_stopped=1
    compose stop ims_web
  fi
fi

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

info "Creating private Project Pulse expense-evidence backup"
compose run --rm --no-deps -T ims_tools sh -c \
  "tar -C /data/pulse_private -czf - ." > "${backup_dir}/pulse-private.tar.gz"
[[ -s "${backup_dir}/pulse-private.tar.gz" ]] || fatal "Project Pulse evidence backup is empty."
resume_web

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

info "Creating permission-restricted recovery configuration bundle (encrypted during off-site upload)"
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
pulse_private_format=tar_gzip
source_format=git_bundle
production_config_format=tar_gzip
web_quiesced=${quiesce_web}
compose_project=ims
payroll_field_key_fingerprint_sha256=${key_fingerprint}
MANIFEST

(
  cd "${backup_dir}"
  sha256sum database.dump media.tar.gz pulse-private.tar.gz source.bundle production-config.tar.gz manifest.txt > SHA256SUMS
  if [[ -f source-working-tree.patch ]]; then
    sha256sum source-working-tree.patch >> SHA256SUMS
  fi
)
chmod 600 "${backup_dir}"/*

bash "${PROJECT_ROOT}/scripts/verify-backup.sh" "${backup_dir}" --require-recovery-bundle
mv -- "${backup_dir}" "${final_backup_dir}"
backup_dir=""
prune_local_backups "${backup_root}" "${retention_days}" "${keep_count}"

printf '%s\n' "${final_backup_dir}"
