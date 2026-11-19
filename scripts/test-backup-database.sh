#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"
umask 077

[[ $# -eq 1 ]] || fatal "Usage: scripts/test-backup-database.sh BACKUP_DIRECTORY"
backup_dir="$1"
[[ "${backup_dir}" == /* ]] || backup_dir="${PROJECT_ROOT}/${backup_dir#./}"
[[ -s "${backup_dir}/database.dump" ]] || fatal "Database dump is missing or empty."
require_environment

# Use the exact locally installed production image, with a completely separate
# container/anonymous data volume. No production mounts, network or credentials.
production_db="$(compose ps -q ims_db)"
[[ -n "${production_db}" ]] || fatal "Production DB container is required to identify the PostgreSQL image."
image="$(docker inspect --format '{{.Image}}' "${production_db}")"
[[ -n "${image}" ]] || fatal "Could not identify the PostgreSQL image."
test_container=""
cleanup() {
  local status=$?
  if [[ -n "${test_container}" ]]; then
    docker rm --force --volumes "${test_container}" >/dev/null || status=1
  fi
  exit "${status}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

info "Creating isolated PostgreSQL restore-test container"
test_container="$(docker create \
  --label ims.backup-restore-test=true \
  --network none --memory 512m --cpus 1 --pids-limit 128 \
  --security-opt no-new-privileges:true \
  --env POSTGRES_HOST_AUTH_METHOD=trust \
  --env POSTGRES_USER=ims_restore_verify \
  --env POSTGRES_DB=ims_restore_verify \
  "${image}" postgres -c shared_buffers=32MB -c max_connections=10)"
docker start "${test_container}" >/dev/null
ready=0
for _ in {1..60}; do
  # Explicit TCP avoids the image entrypoint's temporary socket-only init server.
  if docker exec "${test_container}" pg_isready --host=127.0.0.1 \
    --username=ims_restore_verify --dbname=ims_restore_verify >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
(( ready )) || fatal "Isolated PostgreSQL did not become ready within 120 seconds."

info "Restoring complete database archive into isolated PostgreSQL"
docker exec -i "${test_container}" pg_restore \
  --host=127.0.0.1 --username=ims_restore_verify --dbname=ims_restore_verify \
  --single-transaction --exit-on-error --no-owner --no-privileges \
  < "${backup_dir}/database.dump"

info "Querying restored Django schema and migration data"
migrations="$(docker exec "${test_container}" psql \
  --host=127.0.0.1 --username=ims_restore_verify --dbname=ims_restore_verify \
  --no-psqlrc --tuples-only --no-align --set=ON_ERROR_STOP=1 \
  --command='SELECT count(*) FROM public.django_migrations;')"
[[ "${migrations}" =~ ^[1-9][0-9]*$ ]] || fatal "Restored database has no Django migration history."
printf 'Database restore test passed (%s migration records).\n' "${migrations}"
