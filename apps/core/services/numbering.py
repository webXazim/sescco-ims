from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.models import NumberSequence

SEQUENCE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,79}$")


def _validate_sequence_configuration(*, key: str, prefix: str, padding: int) -> tuple[str, str, int]:
    normalized_key = key.strip().lower()
    normalized_prefix = prefix.strip().upper()
    if not SEQUENCE_KEY_RE.fullmatch(normalized_key):
        raise ValidationError({"key": "Use lowercase letters, numbers, dots, colons, underscores or hyphens."})
    if len(normalized_prefix) > 24:
        raise ValidationError({"prefix": "Prefix cannot exceed 24 characters."})
    if padding < 1 or padding > 18:
        raise ValidationError({"padding": "Padding must be between 1 and 18."})
    return normalized_key, normalized_prefix, padding


@transaction.atomic
def configure_number_sequence(*, company, key: str, prefix: str = "", padding: int = 6) -> NumberSequence:
    key, prefix, padding = _validate_sequence_configuration(key=key, prefix=prefix, padding=padding)
    try:
        sequence = NumberSequence.objects.select_for_update().get(company=company, key=key)
        created = False
    except NumberSequence.DoesNotExist:
        try:
            with transaction.atomic():
                sequence = NumberSequence.objects.create(company=company, key=key, prefix=prefix, padding=padding)
            created = True
        except IntegrityError:
            sequence = NumberSequence.objects.select_for_update().get(company=company, key=key)
            created = False

    if not created:
        if sequence.last_issued_value and (sequence.prefix != prefix or sequence.padding != padding):
            raise ValidationError("Number sequence formatting cannot change after numbers have been issued.")
        changed = []
        if sequence.prefix != prefix:
            sequence.prefix = prefix
            changed.append("prefix")
        if sequence.padding != padding:
            sequence.padding = padding
            changed.append("padding")
        if changed:
            sequence.save(update_fields=(*changed, "updated_at"))
    return sequence


@transaction.atomic
def allocate_number(*, company, key: str, prefix: str = "", padding: int = 6) -> str:
    """Atomically issue the next company-scoped human-readable identifier."""

    key, prefix, padding = _validate_sequence_configuration(key=key, prefix=prefix, padding=padding)
    try:
        sequence = NumberSequence.objects.select_for_update().get(company=company, key=key)
    except NumberSequence.DoesNotExist:
        try:
            with transaction.atomic():
                sequence = NumberSequence.objects.create(company=company, key=key, prefix=prefix, padding=padding)
        except IntegrityError:
            sequence = NumberSequence.objects.select_for_update().get(company=company, key=key)

    if sequence.prefix != prefix or sequence.padding != padding:
        if sequence.last_issued_value:
            raise ValidationError("Requested number format does not match the existing sequence.")
        sequence.prefix = prefix
        sequence.padding = padding

    value = sequence.next_value
    sequence.last_issued_value = value
    sequence.next_value = value + 1
    sequence.save(update_fields=("prefix", "padding", "last_issued_value", "next_value", "updated_at"))
    return f"{sequence.prefix}{value:0{sequence.padding}d}"
