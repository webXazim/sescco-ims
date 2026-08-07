"""Gunicorn runtime configuration for the inventory service."""

from __future__ import annotations

import os


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


bind = "0.0.0.0:8000"
workers = env_int("GUNICORN_WORKERS", 2)
threads = env_int("GUNICORN_THREADS", 2)
worker_class = "gthread"
timeout = env_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)
worker_tmp_dir = "/dev/shm"
preload_app = False
capture_output = True
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = (
    '%({x-request-id}i)s %(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(L)s'
)
