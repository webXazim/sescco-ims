#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${IMS_ENV_FILE:-${PROJECT_ROOT}/.env.production}"
COMPOSE_FILES=(--file "${PROJECT_ROOT}/docker-compose.yml")

read_env_file_value() {
  local file="$1"
  local key="$2"
  [[ -f "${file}" ]] || return 0
  awk -F= -v key="${key}" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]"\047]+|[[:space:]"\047]+$/, "")
      print
      exit
    }
  ' "${file}"
}

shared_proxy_setting="${IMS_USE_SHARED_PROXY:-}"
if [[ -z "${shared_proxy_setting}" ]]; then
  shared_proxy_setting="$(read_env_file_value "${ENV_FILE}" IMS_USE_SHARED_PROXY)"
fi
if [[ "${shared_proxy_setting:-0}" == "1" ]]; then
  COMPOSE_FILES+=(--file "${PROJECT_ROOT}/docker-compose.proxy.yml")
fi

compose() {
  docker compose --env-file "${ENV_FILE}" "${COMPOSE_FILES[@]}" "$@"
}

fatal() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fatal "Required command not found: $1"
}

require_environment() {
  [[ -f "${ENV_FILE}" ]] || fatal "Environment file not found: ${ENV_FILE}"
  require_command docker
  docker compose version >/dev/null 2>&1 || fatal "Docker Compose v2 is required."
}

read_env_value() {
  read_env_file_value "${ENV_FILE}" "$1"
}

wait_for_service_health() {
  local service="$1"
  local timeout_seconds="${2:-180}"
  local container_id elapsed=0 status
  container_id="$(compose ps -q "${service}")"
  [[ -n "${container_id}" ]] || fatal "Service ${service} has no running container."

  while (( elapsed < timeout_seconds )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
    case "${status}" in
      healthy|running)
        return 0
        ;;
      unhealthy|exited|dead)
        compose logs --tail=120 "${service}" >&2 || true
        fatal "Service ${service} entered state: ${status}"
        ;;
    esac
    sleep 3
    elapsed=$((elapsed + 3))
  done

  compose logs --tail=120 "${service}" >&2 || true
  fatal "Timed out waiting for ${service} to become healthy."
}
