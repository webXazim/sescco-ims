from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import CompanyOwnedModel

from .base import (
    ImmutableSourcingRevisionManager,
    SourcingAvailability,
    SourcingEntityStatus,
    SourcingLifecycleModel,
    SourcingRateMixin,
    clean_text,
    normalize_text,
)


class SourcingRateBasis(models.TextChoices):
    HOUR = "hour", "Hour"
    DAY = "day", "Day"
    MONTH = "month", "Month"


class SourcingManpowerSupplier(SourcingLifecycleModel):
    """Reference-only manpower source; intentionally separate from rental_manpower.ManpowerSupplier."""

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False)
    primary_contact_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    mobile = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    cr_number = models.CharField(max_length=60, blank=True)
    vat_number = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "sourcing_manpower_supplier"
        ordering = ("name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_mps_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_mps_company_name_uq"),
            models.UniqueConstraint(
                fields=("company", "cr_number"),
                condition=~Q(cr_number=""),
                name="src_mps_company_cr_uq",
            ),
            models.UniqueConstraint(
                fields=("company", "vat_number"),
                condition=~Q(vat_number=""),
                name="src_mps_company_vat_uq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SourcingEntityStatus.choices]),
                name="src_mps_status_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "normalized_name"), name="src_mps_status_name_idx"),
            models.Index(fields=("company", "deleted_at", "normalized_name"), name="src_mps_trash_name_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_mps_verified_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.primary_contact_name = clean_text(self.primary_contact_name)
        self.phone = clean_text(self.phone)
        self.mobile = clean_text(self.mobile)
        self.email = clean_text(self.email).lower()
        self.city = clean_text(self.city)
        self.region = clean_text(self.region)
        self.cr_number = clean_text(self.cr_number).upper()
        self.vat_number = clean_text(self.vat_number).upper()
        self.notes = (self.notes or "").strip()
        errors = {}
        if not self.code:
            errors["code"] = "Manpower supplier code is required."
        if not self.name:
            errors["name"] = "Manpower supplier name is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class SourcingManpowerContact(CompanyOwnedModel):
    """Sourcing-only contact person attached to a reference Manpower Supplier."""

    supplier = models.ForeignKey(SourcingManpowerSupplier, on_delete=models.CASCADE, related_name="contacts")
    salutation = models.CharField(max_length=20, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    work_phone = models.CharField(max_length=40, blank=True)
    mobile = models.CharField(max_length=40, blank=True)
    is_primary = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_manpower_contact"
        ordering = ("-is_primary", "first_name", "last_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("supplier",),
                condition=Q(is_primary=True, is_active=True),
                name="src_mps_one_primary_contact_uq",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "supplier", "is_active"), name="src_mpcontact_supplier_active_idx"),
            models.Index(fields=("company", "email"), name="src_mpcontact_email_idx"),
            models.Index(fields=("company", "mobile"), name="src_mpcontact_mobile_idx"),
        ]

    @property
    def full_name(self) -> str:
        return clean_text(f"{self.first_name} {self.last_name}")

    def clean(self) -> None:
        super().clean()
        self.salutation = clean_text(self.salutation)
        self.first_name = clean_text(self.first_name)
        self.last_name = clean_text(self.last_name)
        self.designation = clean_text(self.designation)
        self.department = clean_text(self.department)
        self.email = clean_text(self.email).lower()
        self.work_phone = clean_text(self.work_phone)
        self.mobile = clean_text(self.mobile)
        errors = {}
        if not self.first_name:
            errors["first_name"] = "First name is required."
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            errors["supplier"] = "Manpower contact must belong to the same company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name


class SourcingTrade(CompanyOwnedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False)
    category = models.CharField(max_length=120, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    normalized_aliases = models.TextField(blank=True, editable=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_trade"
        ordering = ("category", "name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_trade_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_trade_company_name_uq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "normalized_name"), name="src_trade_active_name_idx"),
            models.Index(fields=("company", "category", "normalized_name"), name="src_trade_cat_name_idx"),
            models.Index(fields=("company", "is_active", "category", "normalized_name"), name="src_trade_scale_find_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.category = clean_text(self.category)
        self.notes = (self.notes or "").strip()
        aliases = []
        normalized_aliases = []
        seen = {self.normalized_name}
        for raw in self.aliases or []:
            alias = clean_text(raw)
            normalized = normalize_text(alias)
            if alias and normalized not in seen:
                aliases.append(alias)
                normalized_aliases.append(normalized)
                seen.add(normalized)
        self.aliases = aliases
        self.normalized_aliases = "\n".join(normalized_aliases)
        errors = {}
        if not self.code:
            errors["code"] = "Trade code is required."
        if not self.name:
            errors["name"] = "Trade name is required."

        # Keep worker terminology controlled inside each company. The same normalized
        # name/alias cannot describe two Sourcing trades (for example AC Technician
        # and A/C Technician should resolve to one canonical trade).
        if self.company_id and self.name:
            candidates = (
                type(self).objects.filter(company_id=self.company_id)
                .exclude(pk=self.pk)
                .values_list("code", "normalized_name", "normalized_aliases")
            )
            own_terms = {self.normalized_name, *normalized_aliases}
            for other_code, other_name, other_alias_blob in candidates:
                other_terms = {other_name, *(line for line in (other_alias_blob or "").splitlines() if line)}
                if own_terms.intersection(other_terms):
                    errors["aliases"] = (
                        f"Trade name/alias conflicts with {other_code}. "
                        "Use one controlled Sourcing Trade for the same worker type."
                    )
                    break
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class SourcingWorkforceOffer(SourcingRateMixin, CompanyOwnedModel):
    supplier = models.ForeignKey(
        SourcingManpowerSupplier,
        on_delete=models.PROTECT,
        related_name="workforce_offers",
    )
    trade = models.ForeignKey(SourcingTrade, on_delete=models.PROTECT, related_name="supplier_offers")
    available_quantity = models.PositiveIntegerField(null=True, blank=True)
    availability = models.CharField(
        max_length=16,
        choices=SourcingAvailability.choices,
        default=SourcingAvailability.UNKNOWN,
        db_index=True,
    )
    rate_basis = models.CharField(max_length=12, choices=SourcingRateBasis.choices, default=SourcingRateBasis.MONTH)
    overtime_rate = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    mobilization_lead_time = models.CharField(max_length=120, blank=True)
    work_location = models.CharField(max_length=160, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourcing_workforce_offers_verified",
    )
    verification_note = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_workforce_offer"
        ordering = ("supplier__name", "trade__name")
        constraints = [
            models.UniqueConstraint(fields=("company", "supplier", "trade"), name="src_workforce_offer_identity_uq"),
            models.CheckConstraint(
                condition=Q(rate__isnull=True) | Q(rate__gte=0),
                name="src_workforce_rate_nonneg_ck",
            ),
            models.CheckConstraint(
                condition=Q(overtime_rate__isnull=True) | Q(overtime_rate__gte=0),
                name="src_workforce_ot_nonneg_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "trade", "availability", "is_active"), name="src_workforce_trade_find_idx"),
            models.Index(fields=("company", "supplier", "is_active"), name="src_workforce_supplier_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_workforce_verified_idx"),
            models.Index(fields=("company", "is_active", "trade", "last_verified_at"), name="src_work_trade_ver_idx"),
            models.Index(fields=("company", "is_active", "supplier", "last_verified_at"), name="src_work_sup_ver_idx"),
            models.Index(fields=("company", "is_active", "availability", "last_verified_at"), name="src_work_avail_ver_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.mobilization_lead_time = clean_text(self.mobilization_lead_time)
        self.work_location = clean_text(self.work_location)
        self.verification_note = clean_text(self.verification_note)
        self.notes = (self.notes or "").strip()
        errors = self.clean_rate_fields()
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            errors["supplier"] = "Manpower supplier must belong to the same company."
        if self.trade_id and self.company_id and self.trade.company_id != self.company_id:
            errors["trade"] = "Trade must belong to the same company."
        if self.overtime_rate is not None and self.overtime_rate < 0:
            errors["overtime_rate"] = "Overtime rate cannot be negative."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.supplier} · {self.trade}"


class SourcingWorkforceOfferRevision(CompanyOwnedModel):
    """Immutable reference history for workforce availability/rate verification."""

    offer = models.ForeignKey(
        SourcingWorkforceOffer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revisions",
    )
    offer_id_snapshot = models.UUIDField(db_index=True)
    supplier_id_snapshot = models.UUIDField(db_index=True)
    trade_id_snapshot = models.UUIDField(db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourcing_workforce_offer_revisions",
    )
    contact_name = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)

    objects = ImmutableSourcingRevisionManager()

    class Meta:
        db_table = "sourcing_workforce_offer_revision"
        ordering = ("-verified_at", "-created_at")
        indexes = [
            models.Index(fields=("company", "offer_id_snapshot", "-verified_at"), name="src_work_rev_offer_idx"),
            models.Index(fields=("company", "supplier_id_snapshot", "-verified_at"), name="src_work_rev_supplier_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Sourcing workforce revisions are immutable.")
        self.contact_name = clean_text(self.contact_name)
        self.note = clean_text(self.note)
        if self.offer_id:
            if self.offer.company_id != self.company_id:
                raise ValidationError({"offer": "Workforce revision must belong to the same company."})
            self.offer_id_snapshot = self.offer_id
            self.supplier_id_snapshot = self.offer.supplier_id
            self.trade_id_snapshot = self.offer.trade_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Sourcing workforce revisions are immutable.")
