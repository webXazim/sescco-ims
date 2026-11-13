#!/usr/bin/env bash
# Non-destructive Project Pulse release check. Run in configured staging
# environment with Django dependencies and a test-capable PostgreSQL account.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

python scripts/project_pulse_u10_offline_checks.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py test apps.project_pulse

echo "Project Pulse U10 source, schema planning, and Django regression suite passed."
echo "Continue with manual staging/security and backup-restore acceptance checks."
