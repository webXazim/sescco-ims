from __future__ import annotations

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.utils import NotSupportedError

from apps.core.models import CompanyOwnedModel


_whitespace_re = re.compile(r"\s+")


def clean_text(value: object) -> str:
    return _whitespace_re.sub(" ", str(value or "").strip())


def normalize_text(value: object) -> str:
    return clean_text(value).casefold()


class SourcingEntityStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class SourcingAvailability(models.TextChoices):
    AVAILABLE = "available", "Available"
    LIMITED = "limited", "Limited"
    UNAVAILABLE = "unavailable", "Unavailable"
    UNKNOWN = "unknown", "Unknown"


class SourcingLifecycleModel(CompanyOwnedModel):
    """Lifecycle base for Sourcing masters only.

    Sourcing is an independent reference directory. These fields deliberately do not
    reuse Inventory or Rental Manpower masters, so archiving or trashing a sourcing
    source never mutates an operational supplier, stock, worker or payroll record.
    """

    status = models.CharField(
        max_length=16,
        choices=SourcingEntityStatus.choices,
        default=SourcingEntityStatus.ACTIVE,
        db_index=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_reason = models.CharField(max_length=300, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purge_after = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_reason = models.CharField(max_length=500, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_deleted_records",
    )

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        self.archived_reason = clean_text(self.archived_reason)
        self.deletion_reason = clean_text(self.deletion_reason)
        if self.deleted_at and not self.purge_after:
            raise ValidationError({"purge_after": "Trash records require a purge date."})
        if self.purge_after and not self.deleted_at:
            raise ValidationError({"deleted_at": "A purge date is only valid for a Trash record."})


class ImmutableSourcingRevisionQuerySet(models.QuerySet):
    def for_company(self, company):
        company_id = getattr(company, "pk", company)
        return self.filter(company_id=company_id)

    def update(self, **kwargs):
        raise NotSupportedError("Sourcing verification history is immutable and cannot be updated.")

    def delete(self):
        raise NotSupportedError("Sourcing verification history is immutable and cannot be deleted.")


class ImmutableSourcingRevisionManager(models.Manager.from_queryset(ImmutableSourcingRevisionQuerySet)):
    pass


class SourcingRateMixin(models.Model):
    """Shared non-transactional quotation fields for sourcing offers."""

    rate = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3, default="SAR")
    rate_valid_until = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean_rate_fields(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        self.currency = clean_text(self.currency).upper() or "SAR"
        if len(self.currency) != 3:
            errors["currency"] = "Currency must be a three-letter code."
        if self.rate is not None and Decimal(self.rate) < 0:
            errors["rate"] = "Rate cannot be negative."
        return errors
