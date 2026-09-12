#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n==> Verifying Upgrade 12 production freeze\n'
bash "${ROOT}/scripts/verify-production-freeze.sh"

# Compatibility wrapper retained for operators that already use the Upgrade 12
# command. The canonical deployment script now performs the same freeze check
# itself before preflight, backup, release tasks and live smoke checks.
exec bash "${ROOT}/scripts/deploy-production.sh" "$@"
