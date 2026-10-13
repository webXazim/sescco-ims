"""Independent, company-owned service sourcing reference models.

No relationship to operational projects, Inventory or financial transactions.
The directory is deliberately not connected to vendor/manpower masters.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import CompanyOwnedModel
from .base import (
    ImmutableSourcingRevisionManager, SourcingAvailability, SourcingEntityStatus,
    SourcingLifecycleModel, SourcingRateMixin, clean_text, normalize_text,
)


class SourcingSubcontractor(SourcingLifecycleModel):
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
    service_coverage = models.CharField(max_length=255, blank=True)
    cr_number = models.CharField(max_length=60, blank=True)
    vat_number = models.CharField(max_length=60, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "sourcing_subcontractor"
        ordering = ("normalized_name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_subco_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_subco_company_name_uq"),
            models.UniqueConstraint(fields=("company", "cr_number"), condition=~Q(cr_number=""), name="src_subco_company_cr_uq"),
            models.UniqueConstraint(fields=("company", "vat_number"), condition=~Q(vat_number=""), name="src_subco_company_vat_uq"),
            models.CheckConstraint(condition=Q(status__in=[value for value, _ in SourcingEntityStatus.choices]), name="src_subco_status_ck"),
        ]
        indexes = [
            models.Index(fields=("company", "status", "normalized_name"), name="src_subco_status_name_idx"),
            models.Index(fields=("company", "deleted_at", "normalized_name"), name="src_subco_trash_name_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_subco_verified_idx"),
        ]

    def clean(self):
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.display_name = clean_text(self.display_name) or self.name
        for field in ("primary_contact_name", "company_phone", "mobile", "address", "street_number", "district", "city", "region", "postal_code", "service_coverage", "website"):
            setattr(self, field, clean_text(getattr(self, field)))
        for field in ("company_email", "email"):
            setattr(self, field, clean_text(getattr(self, field)).lower())
        for field in ("cr_number", "vat_number"):
            setattr(self, field, clean_text(getattr(self, field)).upper())
        self.notes = (self.notes or "").strip()
        errors = {}
        if not self.code:
            errors["code"] = "Subcontractor code is required."
        if not self.name:
            errors["name"] = "Subcontractor name is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} · {self.display_name or self.name}"


class SourcingSubcontractorContact(CompanyOwnedModel):
    subcontractor = models.ForeignKey(SourcingSubcontractor, on_delete=models.CASCADE, related_name="contacts")
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
        db_table = "sourcing_subcontractor_contact"
        ordering = ("-is_primary", "first_name", "last_name", "id")
        constraints = [
            models.UniqueConstraint(fields=("subcontractor",), condition=Q(is_primary=True, is_active=True), name="src_subco_primary_contact_uq"),
        ]
        indexes = [
            models.Index(fields=("company", "subcontractor", "is_active"), name="src_subco_contact_active_idx"),
            models.Index(fields=("company", "email"), name="src_subco_contact_email_idx"),
        ]

    @property
    def full_name(self):
        return clean_text(f"{self.first_name} {self.last_name}")

    def clean(self):
        super().clean()
        for field in ("salutation", "first_name", "last_name", "designation", "department", "work_phone", "mobile"):
            setattr(self, field, clean_text(getattr(self, field)))
        self.email = clean_text(self.email).lower()
        errors = {}
        if not self.first_name:
            errors["first_name"] = "First name is required."
        if self.subcontractor_id and self.company_id and self.subcontractor.company_id != self.company_id:
            errors["subcontractor"] = "Contact must belong to the same company as the subcontractor."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class SourcingServiceRateBasis(models.TextChoices):
    HOUR = "hour", "Hour"
    DAY = "day", "Day"
    VISIT = "visit", "Visit"
    JOB = "job", "Job"
    M2 = "m2", "Square metre"
    M3 = "m3", "Cubic metre"
    MONTH = "month", "Month"
    QUOTATION = "quotation", "Quotation"


class SourcingService(CompanyOwnedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    normalized_name = models.CharField(max_length=200, editable=False)
    category = models.CharField(max_length=120, blank=True)
    default_rate_basis = models.CharField(max_length=24, choices=SourcingServiceRateBasis.choices, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    normalized_aliases = models.TextField(blank=True, editable=False)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_service"
        ordering = ("category", "normalized_name", "code")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="src_service_company_code_uq"),
            models.UniqueConstraint(fields=("company", "normalized_name"), name="src_service_company_name_uq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "normalized_name"), name="src_service_active_name_idx"),
            models.Index(fields=("company", "category", "normalized_name"), name="src_service_category_idx"),
        ]

    def clean(self):
        super().clean()
        self.code = clean_text(self.code).upper()
        self.name = clean_text(self.name)
        self.normalized_name = normalize_text(self.name)
        self.category = clean_text(self.category)
        self.default_rate_basis = clean_text(self.default_rate_basis).lower()
        self.description = (self.description or "").strip()
        self.notes = (self.notes or "").strip()
        if not isinstance(self.aliases, list) or any(not isinstance(item, str) for item in self.aliases):
            raise ValidationError({"aliases": "Aliases must be a list of text values."})
        aliases, normalized_aliases, seen = [], [], {self.normalized_name}
        for value in self.aliases:
            alias, key = clean_text(value), normalize_text(value)
            if alias and key not in seen:
                aliases.append(alias)
                normalized_aliases.append(key)
                seen.add(key)
        self.aliases = aliases
        self.normalized_aliases = "\n".join(normalized_aliases)
        errors = {}
        if not self.code:
            errors["code"] = "Service code is required."
        if not self.name:
            errors["name"] = "Service name is required."
        if self.company_id and self.name:
            for code, name, alias_blob in type(self).objects.filter(company_id=self.company_id).exclude(pk=self.pk).values_list("code", "normalized_name", "normalized_aliases"):
                other_terms = {name, *(line for line in (alias_blob or "").splitlines() if line)}
                if seen.intersection(other_terms):
                    errors["aliases"] = f"Service name/alias conflicts with {code}."
                    break
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} · {self.name}"


class SourcingSubcontractorService(SourcingRateMixin, CompanyOwnedModel):
    subcontractor = models.ForeignKey(SourcingSubcontractor, on_delete=models.PROTECT, related_name="service_offers")
    service = models.ForeignKey(SourcingService, on_delete=models.PROTECT, related_name="subcontractor_offers")
    scope_description = models.CharField(max_length=300, blank=True)
    service_location = models.CharField(max_length=160, blank=True)
    availability = models.CharField(max_length=16, choices=SourcingAvailability.choices, default=SourcingAvailability.UNKNOWN, db_index=True)
    rate_basis = models.CharField(max_length=24, choices=SourcingServiceRateBasis.choices, default=SourcingServiceRateBasis.QUOTATION)
    lead_time = models.CharField(max_length=120, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True, db_index=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sourcing_subcontractor_services_verified")
    verification_note = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "sourcing_subcontractor_service"
        ordering = ("subcontractor__normalized_name", "service__normalized_name", "scope_description")
        constraints = [
            models.UniqueConstraint(fields=("company", "subcontractor", "service", "scope_description", "service_location"), name="src_subservice_identity_uq"),
            models.CheckConstraint(condition=Q(rate__isnull=True) | Q(rate__gte=0), name="src_subservice_rate_nonneg_ck"),
        ]
        indexes = [
            models.Index(fields=("company", "service", "availability", "is_active"), name="src_subsvc_service_find_idx"),
            models.Index(fields=("company", "subcontractor", "is_active"), name="src_subsvc_subco_active_idx"),
            models.Index(fields=("company", "last_verified_at"), name="src_subsvc_verified_idx"),
        ]

    def clean(self):
        super().clean()
        self.scope_description = clean_text(self.scope_description)
        self.service_location = clean_text(self.service_location)
        self.rate_basis = clean_text(self.rate_basis).lower()
        self.lead_time = clean_text(self.lead_time)
        self.verification_note = clean_text(self.verification_note)
        self.notes = (self.notes or "").strip()
        errors = self.clean_rate_fields()
        if self.subcontractor_id and self.company_id and self.subcontractor.company_id != self.company_id:
            errors["subcontractor"] = "Subcontractor belongs to another company."
        if self.service_id and self.company_id and self.service.company_id != self.company_id:
            errors["service"] = "Service belongs to another company."
        if self.rate_basis not in SourcingServiceRateBasis.values:
            errors["rate_basis"] = "Invalid rate basis."
        # The DB constraint covers exact duplicates; this check also rejects
        # case-only scope/location variants inside one company and service.
        if self.company_id and self.subcontractor_id and self.service_id:
            duplicate = type(self).objects.for_company(self.company_id).filter(
                subcontractor_id=self.subcontractor_id, service_id=self.service_id,
                scope_description__iexact=self.scope_description,
                service_location__iexact=self.service_location,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["service"] = "This service/scope/location combination is already in this subcontractor's catalog."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subcontractor} · {self.service}"


class SourcingSubcontractorServiceRevision(CompanyOwnedModel):
    """Append-only verification evidence; snapshots survive service offer removal."""
    offer = models.ForeignKey(SourcingSubcontractorService, null=True, blank=True, on_delete=models.SET_NULL, related_name="revisions")
    offer_id_snapshot = models.UUIDField(db_index=True)
    subcontractor_id_snapshot = models.UUIDField(db_index=True)
    service_id_snapshot = models.UUIDField(db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sourcing_subcontractor_service_revisions")
    contact_name = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)

    objects = ImmutableSourcingRevisionManager()

    class Meta:
        db_table = "sourcing_subcontractor_service_revision"
        ordering = ("-verified_at", "-created_at")
        indexes = [
            models.Index(fields=("company", "offer_id_snapshot", "-verified_at"), name="src_subsvc_rev_offer_idx"),
            models.Index(fields=("company", "subcontractor_id_snapshot", "-verified_at"), name="src_subsvc_rev_subco_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Service verification revisions are immutable.")
        self.contact_name = clean_text(self.contact_name)
        self.note = clean_text(self.note)
        if self.offer_id:
            if self.offer.company_id != self.company_id:
                raise ValidationError({"offer": "Revision belongs to another company."})
            self.offer_id_snapshot = self.offer_id
            self.subcontractor_id_snapshot = self.offer.subcontractor_id
            self.service_id_snapshot = self.offer.service_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Service verification revisions are immutable.")


class SourcingSubcontractorVerificationRevision(CompanyOwnedModel):
    """Immutable confirmation of COMPANY details, separate from each service offer.

    Null-on-delete profile link preserves the company's verified snapshot after
    a permitted directory deletion. Never used to confirm service pricing.
    """
    subcontractor = models.ForeignKey(
        SourcingSubcontractor, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="verification_revisions",
    )
    subcontractor_id_snapshot = models.UUIDField(db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    verified_at = models.DateTimeField(db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sourcing_subcontractor_company_verifications",
    )
    contact_name = models.CharField(max_length=160, blank=True)
    note = models.CharField(max_length=500, blank=True)

    objects = ImmutableSourcingRevisionManager()

    class Meta:
        db_table = "sourcing_subcontractor_verification_revision"
        ordering = ("-verified_at", "-created_at")
        indexes = [
            models.Index(
                fields=("company", "subcontractor_id_snapshot", "-verified_at"),
                name="src_subco_rev_verify_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Company verification revisions are immutable.")
        self.contact_name = clean_text(self.contact_name)
        self.note = clean_text(self.note)
        if self.subcontractor_id:
            if self.subcontractor.company_id != self.company_id:
                raise ValidationError({"subcontractor": "Revision belongs to another company."})
            self.subcontractor_id_snapshot = self.subcontractor_id
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Company verification revisions are immutable.")


class SubcontractorQualificationKind(models.TextChoices):
    COMMERCIAL_REGISTRATION = "cr", "Commercial registration"
    LICENSE = "license", "Trade / service license"
    INSURANCE = "insurance", "Insurance"
    TAX = "tax", "Tax / VAT certificate"
    SAFETY = "safety", "Safety certificate"
    TECHNICAL = "technical", "Technical qualification"
    OTHER = "other", "Other qualification"


class SubcontractorQualificationReview(models.TextChoices):
    PENDING = "pending", "Pending review"
    APPROVED = "approved", "Reviewed / accepted"
    REJECTED = "rejected", "Rejected"


class SourcingSubcontractorDocument(CompanyOwnedModel):
    """Private qualification reference; never a transactional/financial document.

    Store only a random storage key, not a public FileField URL. Files are sent
    exclusively by the tenant/permission-protected Sourcing download endpoint.
    """
    subcontractor = models.ForeignKey(
        SourcingSubcontractor, on_delete=models.PROTECT, related_name="qualification_documents",
    )
    kind = models.CharField(max_length=24, choices=SubcontractorQualificationKind.choices)
    title = models.CharField(max_length=200)
    reference_number = models.CharField(max_length=120, blank=True)
    issuer = models.CharField(max_length=160, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=16, choices=SubcontractorQualificationReview.choices,
        default=SubcontractorQualificationReview.PENDING, db_index=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sourcing_subcontractor_documents_reviewed",
    )
    review_note = models.CharField(max_length=500, blank=True)
    original_name = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=350, unique=True, editable=False)
    content_type = models.CharField(max_length=40, editable=False)
    file_size = models.PositiveIntegerField(editable=False)
    sha256 = models.CharField(max_length=64, editable=False)

    class Meta:
        db_table = "sourcing_subcontractor_document"
        ordering = ("expires_on", "title", "id")
        indexes = [
            models.Index(fields=("company", "subcontractor", "expires_on"), name="src_subdoc_expiry_idx"),
            models.Index(fields=("company", "review_status"), name="src_subdoc_review_idx"),
        ]

    @property
    def expired(self):
        from django.utils import timezone
        return bool(self.expires_on and self.expires_on < timezone.localdate())

    @property
    def expires_soon(self):
        from datetime import timedelta
        from django.utils import timezone
        return bool(self.expires_on and timezone.localdate() <= self.expires_on <= timezone.localdate() + timedelta(days=30))

    @property
    def effective_status(self):
        if self.expired:
            return "Expired"
        if self.review_status == SubcontractorQualificationReview.APPROVED:
            return "Reviewed / accepted"
        return self.get_review_status_display()

    def clean(self):
        super().clean()
        for attr in ("title", "reference_number", "issuer", "review_note"):
            setattr(self, attr, clean_text(getattr(self, attr)))
        self.notes = (self.notes or "").strip()
        errors = {}
        if not self.title:
            errors["title"] = "Document title is required."
        if self.subcontractor_id and self.company_id and self.subcontractor.company_id != self.company_id:
            errors["subcontractor"] = "Document must belong to the same company."
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            errors["expires_on"] = "Expiry cannot precede the issue date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
