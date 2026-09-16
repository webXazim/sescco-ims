from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.core.models import CompanyOwnedModel

from .base import clean_text


class SourcingSettings(CompanyOwnedModel):
    """Per-company freshness policy for reference-only Sourcing data."""

    default_currency = models.CharField(max_length=3, default="SAR")
    fresh_for_days = models.PositiveSmallIntegerField(default=7)
    stale_after_days = models.PositiveSmallIntegerField(default=30)

    class Meta:
        db_table = "sourcing_settings"
        constraints = [
            models.UniqueConstraint(fields=("company",), name="src_settings_company_uq"),
            models.CheckConstraint(condition=Q(fresh_for_days__gte=1), name="src_settings_fresh_positive_ck"),
            models.CheckConstraint(condition=Q(stale_after_days__gt=F("fresh_for_days")), name="src_settings_stale_after_fresh_ck"),
        ]

    def clean(self) -> None:
        super().clean()
        self.default_currency = clean_text(self.default_currency).upper() or "SAR"
        errors = {}
        if len(self.default_currency) != 3:
            errors["default_currency"] = "Currency must be a three-letter code."
        if self.fresh_for_days is not None and self.fresh_for_days < 1:
            errors["fresh_for_days"] = "Freshness window must be at least one day."
        if (
            self.fresh_for_days is not None
            and self.stale_after_days is not None
            and self.stale_after_days <= self.fresh_for_days
        ):
            errors["stale_after_days"] = "Stale threshold must be greater than the freshness window."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.company} · Sourcing settings"
