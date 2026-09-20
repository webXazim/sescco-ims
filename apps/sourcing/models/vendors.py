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


class SourcingVendor(SourcingLifecycleModel):
    """Reference-only vendor identity used by the Sourcing Directory.

    This model intentionally has no relationship to ``inventory.Supplier``.
    """

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False)
    display_name = models.CharField(max_length=200, blank=True)
    primary_contact_name = models.CharField(max_length=160, blank=True)
    company_phone = models.CharField(max_length=40, blank=True)
    company_email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    street_number = models.CharField(max_length=40, blank=True)
    district = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    cr_number = models.CharField(max_length=60, blank=True)
    vat_number = models.CharField(max_length=60, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "sourcing_vendor"
        ordering = ("name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_vendor_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_vendor_company_name_uq"),
            models.UniqueConstraint(
                fields=("company", "cr_number"),
                condition=~Q(cr_number=""),
                name="src_vendor_company_cr_uq",
            ),
            models.UniqueConstraint(
                fields=("company", "vat_number"),
                condition=~Q(vat_number=""),
                name="src_vendor_company_vat_uq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SourcingEntityStatus.choices]),
                name="src_vendor_status_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "normalized_name"), name="src_vendor_status_name_idx"),
            models.Index(fields=("company", "deleted_at", "normalized_name"), name="src_vendor_trash_name_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_vendor_verified_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.display_name = clean_text(self.display_name) or self.name
        self.primary_contact_name = clean_text(self.primary_contact_name)
        self.company_phone = clean_text(self.company_phone)
        self.company_email = clean_text(self.company_email).lower()
        self.mobile = clean_text(self.mobile)
        self.email = clean_text(self.email).lower()
        self.address = clean_text(self.address)
        self.street_number = clean_text(self.street_number)
        self.district = clean_text(self.district)
        self.city = clean_text(self.city)
        self.region = clean_text(self.region)
        self.postal_code = clean_text(self.postal_code)
        self.cr_number = clean_text(self.cr_number).upper()
        self.vat_number = clean_text(self.vat_number).upper()
        self.website = clean_text(self.website)
        self.notes = (self.notes or "").strip()
        errors = {}
        if not self.code:
            errors["code"] = "Vendor code is required."
        if not self.name:
            errors["name"] = "Vendor name is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.display_name or self.name}"


class SourcingVendorContact(CompanyOwnedModel):
    """Sourcing-only contact person attached to a reference Vendor."""

    vendor = models.ForeignKey(SourcingVendor, on_delete=models.CASCADE, related_name="contacts")
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
        db_table = "sourcing_vendor_contact"
        ordering = ("-is_primary", "first_name", "last_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("vendor",),
                condition=Q(is_primary=True, is_active=True),
                name="src_vendor_one_primary_contact_uq",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "vendor", "is_active"), name="src_vcontact_vendor_active_idx"),
            models.Index(fields=("company", "email"), name="src_vcontact_email_idx"),
            models.Index(fields=("company", "mobile"), name="src_vcontact_mobile_idx"),
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
        if self.vendor_id and self.company_id and self.vendor.company_id != self.company_id:
            errors["vendor"] = "Vendor contact must belong to the same company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.full_name


class SourcingMaterial(CompanyOwnedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False)
    category = models.CharField(max_length=120, blank=True)
    default_unit = models.CharField(max_length=40, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    normalized_aliases = models.TextField(blank=True, editable=False)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_material"
        ordering = ("category", "name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_material_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_material_company_name_uq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "normalized_name"), name="src_material_active_name_idx"),
            models.Index(fields=("company", "category", "normalized_name"), name="src_material_cat_name_idx"),
            models.Index(fields=("company", "is_active", "category", "normalized_name"), name="src_mat_scale_find_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.category = clean_text(self.category)
        self.default_unit = clean_text(self.default_unit)
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
            errors["code"] = "Material code is required."
        if not self.name:
            errors["name"] = "Material name is required."

        # Exact alias collisions are rejected inside the company. This keeps search
        # vocabulary controlled (for example, AC Cable cannot be an alias for two
        # different Sourcing Materials) without linking to Inventory item masters.
        if self.company_id and self.name:
            candidates = (
                type(self).objects.filter(company_id=self.company_id)
                .exclude(pk=self.pk)
                .values_list("code", "normalized_name", "normalized_aliases")
            )
            own_terms = {self.normalized_name, *normalized_aliases}
            for other_code, other_name, other_alias_blob in candidates:
                other_terms = {other_name, *(line for line in (other_alias_blob or "").splitlines() if line)}
                collision = own_terms.intersection(other_terms)
                if collision:
                    errors["aliases"] = (
                        f"Material name/alias conflicts with {other_code}. "
                        "Use one controlled Sourcing Material for the same search term."
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


class SourcingVendorOffer(SourcingRateMixin, CompanyOwnedModel):
    """Latest reference quotation/availability state for one Vendor + Material identity."""

    vendor = models.ForeignKey(SourcingVendor, on_delete=models.PROTECT, related_name="supply_offers")
    material = models.ForeignKey(SourcingMaterial, on_delete=models.PROTECT, related_name="vendor_offers")
    specification = models.CharField(max_length=240, blank=True)
    brand = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    available_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    minimum_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    availability = models.CharField(
        max_length=16,
        choices=SourcingAvailability.choices,
        default=SourcingAvailability.UNKNOWN,
        db_index=True,
    )
    lead_time = models.CharField(max_length=120, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourcing_vendor_offers_verified",
    )
    verification_note = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_vendor_offer"
        ordering = ("vendor__name", "material__name", "specification", "brand", "model")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "vendor", "material", "specification", "brand", "model"),
                name="src_vendor_offer_identity_uq",
            ),
            models.CheckConstraint(
                condition=Q(available_quantity__isnull=True) | Q(available_quantity__gte=0),
                name="src_vendor_offer_qty_nonneg_ck",
            ),
            models.CheckConstraint(
                condition=Q(minimum_quantity__isnull=True) | Q(minimum_quantity__gte=0),
                name="src_vendor_offer_min_nonneg_ck",
            ),
            models.CheckConstraint(
                condition=Q(rate__isnull=True) | Q(rate__gte=0),
                name="src_vendor_offer_rate_nonneg_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "material", "availability", "is_active"), name="src_offer_material_find_idx"),
            models.Index(fields=("company", "vendor", "is_active"), name="src_offer_vendor_active_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_offer_verified_idx"),
            models.Index(fields=("company", "is_active", "material", "last_verified_at"), name="src_offer_mat_verify_idx"),
            models.Index(fields=("company", "is_active", "vendor", "last_verified_at"), name="src_offer_vnd_verify_idx"),
            models.Index(fields=("company", "is_active", "availability", "last_verified_at"), name="src_offer_avail_ver_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.specification = clean_text(self.specification)
        self.brand = clean_text(self.brand)
        self.model = clean_text(self.model)
        self.unit = clean_text(self.unit) or (clean_text(self.material.default_unit) if self.material_id else "")
        self.lead_time = clean_text(self.lead_time)
        self.verification_note = clean_text(self.verification_note)
        self.notes = (self.notes or "").strip()
        errors = self.clean_rate_fields()
        if self.vendor_id and self.company_id and self.vendor.company_id != self.company_id:
            errors["vendor"] = "Vendor must belong to the same company."
        if self.material_id and self.company_id and self.material.company_id != self.company_id:
            errors["material"] = "Material must belong to the same company."
        if self.available_quantity is not None and self.available_quantity < 0:
            errors["available_quantity"] = "Available quantity cannot be negative."
        if self.minimum_quantity is not None and self.minimum_quantity < 0:
            errors["minimum_quantity"] = "Minimum quantity cannot be negative."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.vendor} · {self.material}"


class SourcingVendorOfferRevision(CompanyOwnedModel):
    """Immutable reference history for Vendor offer verification/update events."""

    offer = models.ForeignKey(
        SourcingVendorOffer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revisions",
    )
    offer_id_snapshot = models.UUIDField(db_index=True)
    vendor_id_snapshot = models.UUIDField(db_index=True)
    material_id_snapshot = models.UUIDField(db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sourcing_vendor_offer_revisions",
    )
    contact_name = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)

    objects = ImmutableSourcingRevisionManager()

    class Meta:
        db_table = "sourcing_vendor_offer_revision"
        ordering = ("-verified_at", "-created_at")
        indexes = [
            models.Index(fields=("company", "offer_id_snapshot", "-verified_at"), name="src_offer_rev_offer_idx"),
            models.Index(fields=("company", "vendor_id_snapshot", "-verified_at"), name="src_offer_rev_vendor_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Sourcing offer revisions are immutable.")
        self.contact_name = clean_text(self.contact_name)
        self.note = clean_text(self.note)
        if self.offer_id:
            if self.offer.company_id != self.company_id:
                raise ValidationError({"offer": "Offer revision must belong to the same company."})
            self.offer_id_snapshot = self.offer_id
            self.vendor_id_snapshot = self.offer.vendor_id
            self.material_id_snapshot = self.offer.material_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Sourcing offer revisions are immutable.")
