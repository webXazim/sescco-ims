#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/verify-backup.sh BACKUP_DIRECTORY [--require-recovery-bundle]

Checks backup checksums, PostgreSQL archive readability, private-media archive
readability, Project Pulse evidence archive and, when present, the source/configuration recovery bundle. This
does not alter production data.
USAGE
}

[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }
backup_dir="$1"
require_recovery_bundle=0
if [[ $# -eq 2 ]]; then
  [[ "$2" == "--require-recovery-bundle" ]] || { usage; exit 2; }
  require_recovery_bundle=1
fi

if [[ "${backup_dir}" != /* ]]; then
  backup_dir="${PROJECT_ROOT}/${backup_dir#./}"
fi
[[ -d "${backup_dir}" ]] || fatal "Backup directory not found: ${backup_dir}"
for file in database.dump media.tar.gz manifest.txt SHA256SUMS; do
  [[ -f "${backup_dir}/${file}" ]] || fatal "Backup is missing ${file}."
done
[[ -s "${backup_dir}/database.dump" ]] || fatal "database.dump is empty."
if grep -qx 'pulse_private_format=tar_gzip' "${backup_dir}/manifest.txt"; then
  [[ -s "${backup_dir}/pulse-private.tar.gz" ]] || fatal "Project Pulse evidence archive missing."
fi

require_environment
require_command sha256sum
require_command tar
require_command git

info "Verifying backup checksums"
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)

info "Verifying PostgreSQL archive readability"
compose up -d ims_db
wait_for_service_health ims_db 120
compose exec -T ims_db pg_restore --list < "${backup_dir}/database.dump" >/dev/null \
  || fatal "database.dump is not a readable PostgreSQL custom-format archive."

info "Verifying private media archive readability"
tar -tzf "${backup_dir}/media.tar.gz" >/dev/null \
  || fatal "media.tar.gz is not a readable gzip/tar archive."

if [[ -f "${backup_dir}/pulse-private.tar.gz" ]]; then
  info "Verifying Project Pulse private evidence archive readability"
  tar -tzf "${backup_dir}/pulse-private.tar.gz" >/dev/null \
    || fatal "pulse-private.tar.gz is not a readable gzip/tar archive."
fi

if [[ -f "${backup_dir}/source.bundle" || -f "${backup_dir}/production-config.tar.gz" ]]; then
  [[ -s "${backup_dir}/source.bundle" ]] || fatal "source.bundle is missing or empty."
  [[ -s "${backup_dir}/production-config.tar.gz" ]] || fatal "production-config.tar.gz is missing or empty."
  info "Verifying source-code and production-configuration recovery bundles"
  git -C "${PROJECT_ROOT}" bundle verify "${backup_dir}/source.bundle" >/dev/null
  tar -tzf "${backup_dir}/production-config.tar.gz" >/dev/null \
    || fatal "production-config.tar.gz is not a readable gzip/tar archive."
elif (( require_recovery_bundle )); then
  fatal "Backup does not include the required source-code and production-configuration recovery bundle."
fi

printf 'Backup verified: %s\n' "${backup_dir}"
