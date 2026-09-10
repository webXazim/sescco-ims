#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_COMPOSE="${ROOT}/docker-compose.yml"
REHEARSAL_COMPOSE="${ROOT}/docker-compose.rehearsal.yml"
ENV_FILE="${IMS_ENV_FILE:-${ROOT}/.env.production}"
PROJECT="ims_merge_rehearsal"
KEEP="${IMS_REHEARSAL_KEEP:-0}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }

usage() {
  cat <<'USAGE'
Usage: scripts/rehearse-production-freeze.sh BACKUP_DIRECTORY [EVIDENCE_DIRECTORY]

Restores an IMS backup into isolated ims_merge_rehearsal volumes, applies the
complete merged Inventory + Payroll migration chain, runs every reconciliation
command and the Django regression suite, and compares protected pre/post row
counts. Production ims_* volumes and networks are never attached.

Set IMS_REHEARSAL_KEEP=1 to keep the isolated rehearsal containers/volumes after
the run for inspection. The default is to remove them even when a check fails.
USAGE
}

[[ $# -ge 1 && $# -le 2 ]] || { usage; exit 2; }
backup_dir="$1"
if [[ "${backup_dir}" != /* ]]; then
  backup_dir="${ROOT}/${backup_dir#./}"
fi
[[ -d "${backup_dir}" ]] || fail "Backup directory not found: ${backup_dir}"
[[ -f "${ENV_FILE}" ]] || fail "Environment file not found: ${ENV_FILE}"
for file in database.dump media.tar.gz manifest.txt SHA256SUMS; do
  [[ -f "${backup_dir}/${file}" ]] || fail "Backup is missing ${file}."
done
[[ -s "${backup_dir}/database.dump" ]] || fail "database.dump is empty."

command -v docker >/dev/null 2>&1 || fail "Docker is required."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."

if [[ $# -eq 2 ]]; then
  evidence_dir="$2"
  [[ "${evidence_dir}" == /* ]] || evidence_dir="${ROOT}/${evidence_dir#./}"
else
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  evidence_dir="${ROOT}/rehearsal-evidence/${timestamp}"
fi
mkdir -p "${evidence_dir}"
chmod 700 "${evidence_dir}"

manifest_value() {
  local key="$1"
  awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${backup_dir}/manifest.txt"
}
read_env_value() {
  local key="$1"
  awk -F= -v key="${key}" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]"\047]+|[[:space:]"\047]+$/, "")
      print
      exit
    }
  ' "${ENV_FILE}"
}

export IMS_ENV_FILE="${ENV_FILE}"
compose_rehearsal() {
  docker compose \
    --project-name "${PROJECT}" \
    --env-file "${ENV_FILE}" \
    --file "${BASE_COMPOSE}" \
    --file "${REHEARSAL_COMPOSE}" \
    "$@"
}

cleanup() {
  status=$?
  if [[ "${KEEP}" != "1" ]]; then
    compose_rehearsal down --volumes --remove-orphans >/dev/null 2>&1 || true
  else
    printf 'Rehearsal resources retained under project %s.\n' "${PROJECT}" >&2
  fi
  exit "${status}"
}
trap cleanup EXIT

info "Verifying backup checksums and encryption-key binding"
(cd "${backup_dir}" && sha256sum --check SHA256SUMS)
[[ "$(manifest_value service)" == "ims" ]] || fail "Backup is not an IMS backup."
[[ "$(manifest_value compose_project)" == "ims" ]] || fail "Backup Compose identity is not ims."
backup_platform="$(manifest_value platform)"
if [[ -n "${backup_platform}" && "${backup_platform}" != "ims-payroll-merged" ]]; then
  fail "Backup platform is not compatible with the merged IMS + Payroll platform."
fi
configured_key="$(read_env_value PAYROLL_FIELD_ENCRYPTION_KEY)"
[[ -n "${configured_key}" ]] || fail "PAYROLL_FIELD_ENCRYPTION_KEY is missing from ${ENV_FILE}."
expected_key_fp="$(manifest_value payroll_field_key_fingerprint_sha256)"
actual_key_fp="$(printf '%s' "${configured_key}" | sha256sum | awk '{print $1}')"
if [[ -n "${expected_key_fp}" && "${expected_key_fp}" != "${actual_key_fp}" ]]; then
  fail "PAYROLL_FIELD_ENCRYPTION_KEY does not match the backup."
fi
if [[ -z "${expected_key_fp}" && "${IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT:-0}" != "1" ]]; then
  fail "Legacy backup has no Payroll key fingerprint; explicitly set IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT=1 only after verifying it predates encrypted Payroll data."
fi

info "Proving the rehearsal Compose graph is isolated from production resources"
resolved="$(compose_rehearsal config)"
for forbidden in 'name: ims_postgres_data' 'name: ims_static_data' 'name: ims_media_data' 'name: ims_edge' 'name: ims_database'; do
  if grep -Fq -- "${forbidden}" <<<"${resolved}"; then
    fail "Rehearsal configuration still references production resource: ${forbidden}"
  fi
done
for required in \
  'name: ims_merge_rehearsal_postgres_data' \
  'name: ims_merge_rehearsal_static_data' \
  'name: ims_merge_rehearsal_media_data' \
  'name: ims_merge_rehearsal_edge' \
  'name: ims_merge_rehearsal_database'; do
  grep -Fq -- "${required}" <<<"${resolved}" || fail "Missing isolated resource: ${required}"
done

info "Resetting only previous rehearsal resources"
compose_rehearsal down --volumes --remove-orphans >/dev/null 2>&1 || true

info "Building current frozen web image and starting isolated PostgreSQL"
compose_rehearsal build ims_web
compose_rehearsal up -d ims_db
container_id="$(compose_rehearsal ps -q ims_db)"
[[ -n "${container_id}" ]] || fail "Rehearsal database container did not start."
for _ in $(seq 1 60); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
  [[ "${health}" == "healthy" ]] && break
  [[ "${health}" =~ ^(unhealthy|exited|dead)$ ]] && fail "Rehearsal database entered state ${health}."
  sleep 2
done
[[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")" == "healthy" ]] \
  || fail "Timed out waiting for rehearsal PostgreSQL."

postgres_db="$(read_env_value POSTGRES_DB)"
postgres_user="$(read_env_value POSTGRES_USER)"
[[ "${postgres_db}" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || fail "Unsafe POSTGRES_DB value."
[[ "${postgres_user}" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || fail "Unsafe POSTGRES_USER value."

info "Validating and restoring database backup into isolated volume"
compose_rehearsal exec -T ims_db pg_restore --list < "${backup_dir}/database.dump" >/dev/null
compose_rehearsal exec -T ims_db sh -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  dropdb --if-exists --force --username="$POSTGRES_USER" "$POSTGRES_DB"
  createdb --username="$POSTGRES_USER" --owner="$POSTGRES_USER" "$POSTGRES_DB"
'
compose_rehearsal exec -T ims_db sh -c '
  export PGPASSWORD="$POSTGRES_PASSWORD"
  pg_restore --single-transaction --exit-on-error --no-owner --no-privileges \
    --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
' < "${backup_dir}/database.dump"

info "Validating and restoring private media into isolated volume"
tar_list="$(compose_rehearsal run --rm --no-deps -T \
  --volume "${backup_dir}:/rehearsal-backup:ro" \
  ims_tools sh -c 'tar -tzf /rehearsal-backup/media.tar.gz')"
if grep -Eq '(^/|(^|/)\.\.(/|$))' <<<"${tar_list}"; then
  fail "media.tar.gz contains an unsafe path."
fi
compose_rehearsal run --rm --no-deps -T \
  --volume "${backup_dir}:/rehearsal-backup:ro" \
  ims_tools sh -c 'rm -rf /data/media/* /data/media/.[!.]* /data/media/..?* 2>/dev/null || true; tar -C /data/media -xzf /rehearsal-backup/media.tar.gz'

run_manage() {
  compose_rehearsal run --rm --no-deps -T -e RUN_STARTUP_TASKS=0 ims_web python manage.py "$@"
}

info "Capturing protected pre-migration IMS row counts and legacy-field fingerprints"
run_manage merge_baseline_report > "${evidence_dir}/before.json"
compose_rehearsal run --rm --no-deps -T -e RUN_STARTUP_TASKS=0 \
  ims_web python scripts/rehearsal-data-fingerprint.py \
  > "${evidence_dir}/data-before.json"

info "Rehearsing complete merge migration chain"
run_manage migrate --plan > "${evidence_dir}/migration-plan.txt"
run_manage migrate --noinput
run_manage migrate --check

info "Running every merged-domain reconciliation gate"
run_manage merge_access_report --fail-on-errors > "${evidence_dir}/access-report.json"
run_manage merge_inventory_tenant_report --fail-on-errors > "${evidence_dir}/inventory-report.json"
run_manage merge_shared_projects_report --fail-on-errors > "${evidence_dir}/projects-report.json"
run_manage merge_internal_payroll_report --fail-on-errors > "${evidence_dir}/internal-payroll-report.txt"
run_manage merge_rental_manpower_report --fail-on-errors > "${evidence_dir}/rental-manpower-report.txt"
run_manage merge_documents_management_report --fail-on-errors > "${evidence_dir}/documents-management-report.txt"
run_manage payroll_bootstrap_report --fail-on-errors > "${evidence_dir}/payroll-bootstrap-report.txt"

info "Running deployment checks, schema drift check and full Django regression suite"
run_manage check --deploy --fail-level ERROR
run_manage makemigrations --check --dry-run
run_manage collectstatic --noinput
run_manage test --noinput

info "Capturing post-migration preservation evidence"
run_manage merge_baseline_report > "${evidence_dir}/after.json"
compose_rehearsal run --rm --no-deps -T -e RUN_STARTUP_TASKS=0 \
  --volume "${evidence_dir}:/rehearsal-evidence:ro" \
  ims_web python scripts/rehearsal-data-fingerprint.py \
  --column-contract /rehearsal-evidence/data-before.json \
  > "${evidence_dir}/data-after.json"
python3 "${ROOT}/scripts/compare-rehearsal-baselines.py" \
  "${evidence_dir}/before.json" "${evidence_dir}/after.json" \
  | tee "${evidence_dir}/row-count-preservation.txt"
python3 "${ROOT}/scripts/compare-rehearsal-fingerprints.py" \
  "${evidence_dir}/data-before.json" "${evidence_dir}/data-after.json" \
  | tee "${evidence_dir}/legacy-data-preservation.txt"

(
  cd "${evidence_dir}"
  sha256sum -- * > SHA256SUMS
)
chmod 600 "${evidence_dir}"/*

info "Upgrade 12 production-freeze rehearsal passed"
printf 'Evidence: %s\n' "${evidence_dir}"
