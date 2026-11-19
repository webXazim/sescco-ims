#!/usr/bin/env bash
# Shared backup policy. Source after lib/compose.sh.
umask 077

backup_setting() {
  local key="$1" fallback="${2:-}" value
  value="${!key:-}"
  [[ -n "${value}" ]] || value="$(read_env_value "${key}")"
  printf '%s' "${value:-${fallback}}"
}

backup_root_path() {
  local root
  root="$(backup_setting IMS_BACKUP_DIR "${PROJECT_ROOT}/backups")"
  [[ "${root}" == /* ]] || root="${PROJECT_ROOT}/${root#./}"
  mkdir -p "${root}"
  (cd "${root}" && pwd -P)
}

prune_local_backups() {
  local root="$1" days="$2" keep="$3" name count=0 cutoff
  (( days > 0 )) || return 0
  cutoff="$(date -u -d "${days} days ago" +%Y%m%dT%H%M%SZ)"
  # Only completed, timestamp-named IMS snapshots; never unrelated directories.
  while IFS= read -r name; do
    [[ "${name}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || continue
    [[ ! -L "${root}/${name}" && -f "${root}/${name}/SHA256SUMS" ]] || continue
    grep -qx 'service=ims' "${root}/${name}/manifest.txt" || continue
    count=$((count + 1))
    if (( count > keep )) && [[ "${name}" < "${cutoff}" ]]; then
      info "Pruning local snapshot ${name}"
      rm -rf -- "${root:?}/${name}"
    fi
  done < <(find "${root}" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort -r)
}
