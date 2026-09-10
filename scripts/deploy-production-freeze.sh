#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\n==> Verifying Upgrade 12 production freeze\n'
bash "${ROOT}/scripts/verify-production-freeze.sh"

# Hand off to the unchanged Upgrade 11 production deployment authority. That
# script runs the historical preflight, backup, release tasks and live smoke
# checks. Keeping it unchanged preserves its frozen infrastructure checksum.
exec bash "${ROOT}/scripts/deploy-production.sh"
