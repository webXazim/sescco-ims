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

if [ "${RUN_STARTUP_TASKS:-1}" = "1" ]; then
    wait_for_database
    python manage.py check --deploy --fail-level ERROR
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput --clear
fi

exec "$@"
