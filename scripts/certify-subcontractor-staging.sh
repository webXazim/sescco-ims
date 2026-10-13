#!/usr/bin/env bash
# Only for staging: restores a backup into the isolated ims_merge_rehearsal Docker project.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
if (( $# < 1 || $# > 2 )); then
  printf 'Usage: %s BACKUP_DIRECTORY [EVIDENCE_DIRECTORY]\n' "$0" >&2
  printf 'Never run against production containers or volumes.\n' >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo 'ERROR: Docker Compose v2 is required for the isolated staging rehearsal.' >&2
  exit 2
fi
python3 scripts/verify-granular-access-authority.py
python3 scripts/verify-subcontractor-release-extension.py
bash scripts/verify-production-freeze.sh
# This existing production-grade rehearsal validates isolated volumes, restores a
# backup, runs migration plan, complete Django tests and row/fingerprint checks.
bash scripts/rehearse-production-freeze.sh "$@"
echo 'Staging database rehearsal complete. Browser checks must also pass on an ISOLATED running staging URL.'
echo 'Use: python3 scripts/certify-subcontractor-browser.py --base-url STAGING_URL --username USER --i-confirm-staging-is-isolated'
