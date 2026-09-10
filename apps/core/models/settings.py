from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import models

from .base import UUIDTimeStampedModel


class CompanySettings(UUIDTimeStampedModel):
    """Validated company-wide defaults shared by Inventory and Payroll."""

    company = models.OneToOneField(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="settings",
    )
    timezone = models.CharField(max_length=64, default="Asia/Riyadh")
    currency_code = models.CharField(max_length=3, default="SAR")
    country_code = models.CharField(max_length=2, default="SA")

    class Meta:
        db_table = "core_company_settings"
        verbose_name_plural = "company settings"

    def clean(self) -> None:
        super().clean()
        self.timezone = self.timezone.strip()
        self.currency_code = self.currency_code.strip().upper()
        self.country_code = self.country_code.strip().upper()

        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": "Enter a valid IANA timezone name."}) from exc

        if len(self.currency_code) != 3 or not self.currency_code.isalpha():
            raise ValidationError({"currency_code": "Currency code must be a three-letter ISO code."})
        if len(self.country_code) != 2 or not self.country_code.isalpha():
            raise ValidationError({"country_code": "Country code must be a two-letter ISO code."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Settings · {self.company}"
