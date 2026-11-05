#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

require_environment
require_command rclone
require_command mktemp

rclone_config="${IMS_OFFSITE_RCLONE_CONFIG:-$(read_env_value IMS_OFFSITE_RCLONE_CONFIG)}"
rclone_remote="${IMS_OFFSITE_RCLONE_REMOTE:-$(read_env_value IMS_OFFSITE_RCLONE_REMOTE)}"
retention_days="${IMS_OFFSITE_BACKUP_RETENTION_DAYS:-$(read_env_value IMS_OFFSITE_BACKUP_RETENTION_DAYS)}"

[[ -n "${rclone_config}" ]] || fatal "IMS_OFFSITE_RCLONE_CONFIG is required for an off-site backup."
[[ -f "${rclone_config}" ]] || fatal "rclone config file not found: ${rclone_config}"
[[ -n "${rclone_remote}" ]] || fatal "IMS_OFFSITE_RCLONE_REMOTE is required for an off-site backup."
[[ "${rclone_remote}" == *: ]] || fatal "IMS_OFFSITE_RCLONE_REMOTE must name an rclone remote ending in a colon."
if [[ -n "${retention_days}" ]]; then
  [[ "${retention_days}" =~ ^[0-9]+$ ]] || fatal "IMS_OFFSITE_BACKUP_RETENTION_DAYS must be a non-negative integer."
fi

backup_log="$(mktemp)"
trap 'rm -f "${backup_log}"' EXIT
info "Creating complete local recovery backup"
bash "${PROJECT_ROOT}/scripts/backup.sh" | tee "${backup_log}"
backup_dir="$(tail -n 1 "${backup_log}")"
[[ -d "${backup_dir}" ]] || fatal "Backup script did not return a valid backup directory."

bash "${PROJECT_ROOT}/scripts/verify-backup.sh" "${backup_dir}" --require-recovery-bundle

backup_name="$(basename "${backup_dir}")"
info "Uploading encrypted backup to ${rclone_remote}${backup_name}"
rclone --config "${rclone_config}" copy \
  --check-first \
  --transfers "${IMS_OFFSITE_RCLONE_TRANSFERS:-2}" \
  --retries 5 \
  --low-level-retries 10 \
  "${backup_dir}" "${rclone_remote}${backup_name}"

info "Verifying encrypted off-site backup"
rclone --config "${rclone_config}" cryptcheck --one-way \
  "${backup_dir}" "${rclone_remote}${backup_name}"

if [[ "${retention_days:-0}" =~ ^[0-9]+$ ]] && (( retention_days > 0 )); then
  info "Pruning only off-site backup files older than ${retention_days} days"
  rclone --config "${rclone_config}" delete --min-age "${retention_days}d" "${rclone_remote}"
  rclone --config "${rclone_config}" rmdirs "${rclone_remote}"
fi

printf 'Off-site backup verified: %s\n' "${backup_dir}"
