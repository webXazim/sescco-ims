#!/usr/bin/env bash
set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/compose.sh"
require_environment
compose exec -e RUN_STARTUP_TASKS=0 ims_web python manage.py createsuperuser
