from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overriding real environment variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


class ImproperEnvironment(RuntimeError):
    """Raised when required deployment configuration is missing or invalid."""


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ImproperEnvironment(f"Required environment variable {name!r} is missing.")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperEnvironment(f"Environment variable {name!r} must be a boolean value.")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ImproperEnvironment(f"Environment variable {name!r} must be an integer.") from exc


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default or [])
    return [value.strip() for value in raw.split(",") if value.strip()]


def database_from_url(url: str, *, base_dir: Path) -> dict[str, object]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in {"sqlite", "sqlite3"}:
        path = unquote(parsed.path)
        if path in {"", "/"}:
            name = base_dir / "db.sqlite3"
        elif path.startswith("//"):
            name = Path(path[1:])
        else:
            name = base_dir / path.lstrip("/")
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": str(name)}
    if scheme not in {"postgres", "postgresql"}:
        raise ImproperEnvironment(f"Unsupported DATABASE_URL scheme: {scheme!r}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "localhost",
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": env_bool("DB_CONN_HEALTH_CHECKS", True),
        "OPTIONS": {"sslmode": env("DB_SSLMODE", "prefer")},
    }


def database_from_environment(*, base_dir: Path) -> dict[str, object]:
    """Build a database config without interpolating passwords into a URL.

    DATABASE_URL remains supported for development and managed platforms. Docker
    production uses discrete DB_* variables so reserved URL characters in strong
    passwords cannot corrupt the connection string.
    """
    database_url = env("DATABASE_URL")
    if database_url:
        return database_from_url(database_url, base_dir=base_dir)

    engine = env("DB_ENGINE", "sqlite").lower()
    if engine in {"sqlite", "sqlite3"}:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(base_dir / env("DB_NAME", "db.sqlite3")),
        }
    if engine not in {"postgres", "postgresql"}:
        raise ImproperEnvironment(f"Unsupported DB_ENGINE: {engine!r}")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", required=True),
        "USER": env("DB_USER", required=True),
        "PASSWORD": env("DB_PASSWORD", required=True),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env_int("DB_PORT", 5432),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": env_bool("DB_CONN_HEALTH_CHECKS", True),
        "OPTIONS": {"sslmode": env("DB_SSLMODE", "prefer")},
    }
