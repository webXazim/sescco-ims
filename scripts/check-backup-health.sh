#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"
source "${PROJECT_ROOT}/scripts/lib/backup.sh"

# Suitable for an existing monitoring agent/SSH probe. No Docker access required.
hours="$(backup_setting IMS_BACKUP_MAX_AGE_HOURS 36)"
[[ "${hours}" =~ ^[1-9][0-9]*$ ]] || fatal "IMS_BACKUP_MAX_AGE_HOURS must be a positive integer."
root="$(backup_root_path)"
[[ -f "${root}/.last-offsite-success" ]] || fatal "No verified off-site backup success has been recorded."
read -r completed verification < "${root}/.last-offsite-success"
[[ "${verification:-}" == restore-tested ]] || fatal "No off-site backup has passed the automated database restore test yet."
[[ "${completed}" =~ ^[0-9]+$ ]] || fatal "Invalid off-site backup success timestamp."
age=$(( $(date -u +%s) - completed ))
(( age >= 0 && age <= hours * 3600 )) || fatal "Verified off-site backup is stale or the host clock is incorrect (age=${age}s)."
printf 'OK: last verified, database-restore-tested off-site backup completed %s hours ago.\n' "$((age / 3600))"
