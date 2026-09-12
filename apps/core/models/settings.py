from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from .base import UUIDTimeStampedModel


def _branding_upload_path(instance, filename: str, kind: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"company-branding/{instance.company_id}/{kind}/{instance.id}.{suffix}"


def company_logo_upload_to(instance, filename: str) -> str:
    return _branding_upload_path(instance, filename, "logo")


def company_letterhead_upload_to(instance, filename: str) -> str:
    return _branding_upload_path(instance, filename, "letterhead")


def company_watermark_upload_to(instance, filename: str) -> str:
    return _branding_upload_path(instance, filename, "watermark")


def document_branding_upload_to(instance, filename: str) -> str:
    """Historical upload callable retained for immutable core.0003 imports."""
    suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in (filename or "") else ".bin"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".bin"
    return f"company-document-assets/{instance.company_id}/{uuid.uuid4().hex}{suffix}"


class DocumentBrandingMode(models.TextChoices):
    STANDARD = "standard", "Standard header"
    LETTERHEAD = "letterhead", "Full-page letterhead"


_BRAND_EXTENSIONS = FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])


def validate_document_branding_size(value) -> None:
    if value and getattr(value, "size", 0) > 12 * 1024 * 1024:
        raise ValidationError("Document branding images must be 12 MB or smaller.")


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
    commercial_registration = models.CharField(max_length=60, blank=True)
    vat_number = models.CharField(max_length=60, blank=True)
    document_address = models.CharField(max_length=400, blank=True)
    document_email = models.EmailField(blank=True)
    document_phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(max_length=300, blank=True)
    document_branding_mode = models.CharField(
        max_length=16, choices=DocumentBrandingMode.choices, default=DocumentBrandingMode.STANDARD
    )
    document_logo = models.FileField(
        upload_to=company_logo_upload_to, blank=True, max_length=180,
        validators=[_BRAND_EXTENSIONS, validate_document_branding_size],
    )
    document_letterhead = models.FileField(
        upload_to=company_letterhead_upload_to, blank=True, max_length=180,
        validators=[_BRAND_EXTENSIONS, validate_document_branding_size],
    )
    document_watermark = models.FileField(
        upload_to=company_watermark_upload_to, blank=True, max_length=180,
        validators=[_BRAND_EXTENSIONS, validate_document_branding_size],
    )

    class Meta:
        db_table = "core_company_settings"
        verbose_name_plural = "company settings"

    def clean(self) -> None:
        super().clean()
        self.timezone = self.timezone.strip()
        self.currency_code = self.currency_code.strip().upper()
        self.country_code = self.country_code.strip().upper()
        self.commercial_registration = self.commercial_registration.strip().upper()
        self.vat_number = self.vat_number.strip().upper()
        self.document_address = " ".join(self.document_address.split())
        self.document_email = self.document_email.strip().lower()
        self.document_phone = self.document_phone.strip()
        self.website = self.website.strip()
        self.document_branding_mode = self.document_branding_mode.strip().lower()
        if self.document_branding_mode not in DocumentBrandingMode.values:
            raise ValidationError({"document_branding_mode": "Select a valid document branding mode."})

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
