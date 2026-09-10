#!/bin/sh
set -eu
umask 027

wait_for_database() {
python - <<'PY'
import os
import socket
import time

host = os.getenv("DB_HOST", "")
port = int(os.getenv("DB_PORT", "5432"))
if not host:
    raise SystemExit(0)
for attempt in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            raise SystemExit(0)
    except OSError:
        if attempt == 59:
            raise
        time.sleep(1)
PY
}

# Startup tasks are disabled by default in production. Deployment/restore run
# scripts/release-tasks.sh explicitly before the web container is replaced.
if [ "${RUN_STARTUP_TASKS:-0}" = "1" ]; then
    wait_for_database
    python manage.py check --deploy --fail-level ERROR
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    # The static volume is read by Nginx in a separate container with a
    # different uid/gid. Repair permissions on both new files and any
    # directories retained from an older deployment.
    chmod -R u=rwX,go=rX /app/staticfiles
fi

exec "$@"
