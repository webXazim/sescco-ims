from __future__ import annotations

import base64
import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = str(getattr(settings, "PAYROLL_FIELD_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        raise ImproperlyConfigured("PAYROLL_FIELD_ENCRYPTION_KEY is required before sensitive payroll fields can be used.")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:  # pragma: no cover - defensive configuration guard
        raise ImproperlyConfigured("PAYROLL_FIELD_ENCRYPTION_KEY must be a valid Fernet key.") from exc
    if len(decoded) != 32:
        raise ImproperlyConfigured("PAYROLL_FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return Fernet(raw.encode("ascii"))


def encrypt_text(value: str | None) -> str | None:
    if value in (None, ""):
        return value
    return _fernet().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value in (None, ""):
        return value
    try:
        return _fernet().decrypt(str(value).encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ImproperlyConfigured("Sensitive payroll data could not be decrypted with the configured key.") from exc


def sensitive_fingerprint(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    raw = str(getattr(settings, "PAYROLL_FIELD_ENCRYPTION_KEY", "") or "").strip()
    if not raw:
        raise ImproperlyConfigured("PAYROLL_FIELD_ENCRYPTION_KEY is required before sensitive payroll fields can be used.")
    key = base64.urlsafe_b64decode(raw.encode("ascii"))
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
