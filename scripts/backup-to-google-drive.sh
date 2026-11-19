#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"
source "${PROJECT_ROOT}/scripts/lib/backup.sh"

require_environment
require_command rclone
require_command mktemp
require_command flock

rclone_config="$(backup_setting IMS_OFFSITE_RCLONE_CONFIG)"
rclone_remote="$(backup_setting IMS_OFFSITE_RCLONE_REMOTE)"
retention_days="$(backup_setting IMS_OFFSITE_BACKUP_RETENTION_DAYS 90)"
transfers="$(backup_setting IMS_OFFSITE_RCLONE_TRANSFERS 2)"
backup_root="$(backup_root_path)"
exec 8>"${backup_root}/.offsite.lock"
flock -n 8 || fatal "Another off-site backup is running."

# Always produce a usable local snapshot, even when the remote is misconfigured.
backup_log="$(mktemp)"
download_dir=""
cleanup() {
  local status=$?
  rm -f "${backup_log}"
  [[ -z "${download_dir}" ]] || rm -rf -- "${download_dir}"
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
info "Creating complete local recovery backup"
bash "${PROJECT_ROOT}/scripts/backup.sh" | tee "${backup_log}"
backup_dir="$(tail -n 1 "${backup_log}")"
[[ -d "${backup_dir}" ]] || fatal "Backup script did not return a valid backup directory."

[[ -n "${rclone_config}" ]] || fatal "IMS_OFFSITE_RCLONE_CONFIG is required for an off-site backup."
[[ -f "${rclone_config}" ]] || fatal "rclone config file not found: ${rclone_config}"
[[ -n "${rclone_remote}" ]] || fatal "IMS_OFFSITE_RCLONE_REMOTE is required for an off-site backup."
[[ "${rclone_remote}" =~ ^[a-zA-Z0-9_-]+:$ ]] || fatal "IMS_OFFSITE_RCLONE_REMOTE must name a dedicated rclone remote ending in a colon."
[[ "${transfers}" =~ ^[1-9][0-9]*$ ]] || fatal "IMS_OFFSITE_RCLONE_TRANSFERS must be a positive integer."
if [[ -n "${retention_days}" ]]; then
  [[ "${retention_days}" =~ ^(0|[1-9][0-9]*)$ ]] || fatal "IMS_OFFSITE_BACKUP_RETENTION_DAYS must be a non-negative integer."
fi

# Fail closed before uploading database/configuration secrets to a plain remote.
remote_type="$(rclone --config "${rclone_config}" listremotes --long | awk -v remote="${rclone_remote}" '$1 == remote {print $2}')"
[[ "${remote_type}" == crypt ]] || fatal "Off-site remote must have rclone type crypt; refusing an unencrypted upload."

backup_name="$(basename "${backup_dir}")"
info "Uploading encrypted backup to ${rclone_remote}${backup_name}"
rclone --config "${rclone_config}" copy \
  --check-first \
  --transfers "${transfers}" \
  --retries 5 \
  --low-level-retries 10 \
  "${backup_dir}" "${rclone_remote}${backup_name}"

info "Verifying encrypted off-site backup"
rclone --config "${rclone_config}" cryptcheck --one-way \
  "${backup_dir}" "${rclone_remote}${backup_name}"

info "Downloading uploaded recovery set for checksums, archives and database restore test"
download_dir="$(mktemp -d "${backup_root}/.restore-check.XXXXXX")"
rclone --config "${rclone_config}" copy \
  --transfers "${transfers}" --retries 5 --low-level-retries 10 \
  "${rclone_remote}${backup_name}" "${download_dir}"
bash "${PROJECT_ROOT}/scripts/verify-backup.sh" "${download_dir}" \
  --require-recovery-bundle --restore-database

if [[ "${retention_days:-0}" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  info "Pruning whole off-site snapshots older than ${retention_days} days"
  cutoff="$(date -u -d "${retention_days} days ago" +%Y%m%dT%H%M%SZ)"
  # Do not prune by file mtime: unchanged environment/config files can be older
  # than the snapshot. A failed listing must fail the job, not look like success.
  remote_dirs="$(rclone --config "${rclone_config}" lsf --dirs-only --max-depth 1 "${rclone_remote}")"
  while IFS= read -r name; do
    name="${name%/}"
    [[ "${name}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || continue
    [[ "${name}" < "${cutoff}" ]] || continue
    rclone --config "${rclone_config}" purge "${rclone_remote}${name}"
  done <<< "${remote_dirs}"
fi

printf '%s restore-tested\n' "$(date -u +%s)" > "${backup_root}/.last-offsite-success.tmp"
mv -- "${backup_root}/.last-offsite-success.tmp" "${backup_root}/.last-offsite-success"
printf 'Off-site backup verified: %s\n' "${backup_dir}"
