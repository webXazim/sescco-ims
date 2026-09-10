from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from .base import UUIDTimeStampedModel


class NumberSequence(UUIDTimeStampedModel):
    """Transaction-safe, company-scoped counter for business document numbers."""

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="number_sequences",
    )
    key = models.CharField(max_length=80)
    prefix = models.CharField(max_length=24, blank=True)
    padding = models.PositiveSmallIntegerField(default=6, validators=[MinValueValidator(1)])
    next_value = models.PositiveBigIntegerField(default=1, validators=[MinValueValidator(1)])
    last_issued_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        db_table = "core_number_sequence"
        ordering = ("company__name", "key")
        constraints = [
            models.UniqueConstraint(fields=("company", "key"), name="core_seq_company_key_uniq"),
            models.CheckConstraint(condition=models.Q(next_value__gt=0), name="core_seq_next_positive"),
            models.CheckConstraint(condition=models.Q(padding__gt=0), name="core_seq_pad_positive"),
        ]
        indexes = [models.Index(fields=("company", "key"), name="core_sequence_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.company} · {self.key}"
