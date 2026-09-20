#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n==> Verifying packaged production freeze\n'
bash "${ROOT}/scripts/verify-production-freeze.sh"

# Compatibility wrapper retained for operators that already use the production-freeze command.
# The canonical deployment script performs the same packaged freeze check before preflight,
# backup, release tasks and live smoke checks.
exec bash "${ROOT}/scripts/deploy-production.sh" "$@"
