from __future__ import annotations

from django.db import models

MONEY_MAX_DIGITS = 18
MONEY_DECIMAL_PLACES = 2
RATE_MAX_DIGITS = 18
RATE_DECIMAL_PLACES = 4
HOURS_MAX_DIGITS = 9
HOURS_DECIMAL_PLACES = 2


def money_field(**kwargs) -> models.DecimalField:
    return models.DecimalField(
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        **kwargs,
    )


def rate_field(**kwargs) -> models.DecimalField:
    return models.DecimalField(
        max_digits=RATE_MAX_DIGITS,
        decimal_places=RATE_DECIMAL_PLACES,
        **kwargs,
    )


def hours_field(**kwargs) -> models.DecimalField:
    return models.DecimalField(
        max_digits=HOURS_MAX_DIGITS,
        decimal_places=HOURS_DECIMAL_PLACES,
        **kwargs,
    )


class EncryptedTextField(models.TextField):
    """Application-level encrypted text stored as Fernet ciphertext in the database."""

    description = "Encrypted text"

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        from apps.core.encryption import decrypt_text
        return decrypt_text(value)

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        from apps.core.encryption import encrypt_text
        return encrypt_text(str(value))
