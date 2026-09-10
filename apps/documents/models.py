from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.db.utils import NotSupportedError

from apps.core.models import CompanyOwnedModel
from apps.core.models.scoping import CompanyScopedQuerySet


class DocumentWorkspace(models.TextChoices):
    INTERNAL = "internal", "Internal Company"
    RENTAL = "rental", "Rental Manpower"


class DocumentType(models.TextChoices):
    SALARY_SLIP = "salary_slip", "Salary Slip"
    INTERNAL_TIMESHEET = "internal_timesheet", "Internal Timesheet"
    SALARY_PAYMENT_RECEIPT = "salary_payment_receipt", "Salary Payment Receipt"
    RENTAL_TIMESHEET = "rental_timesheet", "Rental Timesheet"
    SUPPLIER_SETTLEMENT = "supplier_settlement", "Supplier Settlement"
    SUPPLIER_INVOICE = "supplier_invoice", "Supplier Invoice"
    SUPPLIER_PAYMENT_RECEIPT = "supplier_payment_receipt", "Supplier Payment Receipt"


class DocumentStatus(models.TextChoices):
    FINAL = "final", "Final"


class ImmutableDocumentQuerySet(CompanyScopedQuerySet):
    def update(self, **kwargs):
        raise NotSupportedError("Final business documents are immutable and cannot be updated.")

    def delete(self):
        raise NotSupportedError("Final business documents are immutable and cannot be deleted.")


class ImmutableDocumentManager(models.Manager.from_queryset(ImmutableDocumentQuerySet)):
    pass


class BusinessDocument(CompanyOwnedModel):
    """Immutable printable snapshot of an already-controlled business record.

    Documents never become a second source of financial truth. ``snapshot`` is copied from the
    source ledger at finalization time and is retained only so historical printing remains stable.
    """

    workspace = models.CharField(max_length=16, choices=DocumentWorkspace.choices, db_index=True)
    document_type = models.CharField(max_length=32, choices=DocumentType.choices, db_index=True)
    document_number = models.CharField(max_length=48)
    status = models.CharField(max_length=12, choices=DocumentStatus.choices, default=DocumentStatus.FINAL)
    period_start = models.DateField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=240)
    entity_reference = models.CharField(max_length=80, blank=True)
    entity_name = models.CharField(max_length=240, blank=True)
    source_model = models.CharField(max_length=120)
    source_id = models.UUIDField()
    source_reference = models.CharField(max_length=80, blank=True)
    external_reference = models.CharField(max_length=120, blank=True)
    snapshot = models.JSONField(encoder=DjangoJSONEncoder)
    source_fingerprint = models.CharField(max_length=64)
    snapshot_fingerprint = models.CharField(max_length=64)
    finalized_at = models.DateTimeField()
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="finalized_payroll_documents",
    )

    objects = ImmutableDocumentManager()

    class Meta:
        db_table = "documents_business_document"
        ordering = ("-finalized_at", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("company", "document_number"), name="doc_company_number_uniq"),
            models.UniqueConstraint(
                fields=("company", "document_type", "source_model", "source_id"),
                name="doc_source_type_uniq",
            ),
            models.UniqueConstraint(
                fields=("company", "document_type", "entity_reference", "external_reference"),
                condition=~Q(external_reference=""),
                name="doc_external_ref_uniq",
            ),
            models.CheckConstraint(
                condition=Q(workspace__in=[value for value, _ in DocumentWorkspace.choices]),
                name="doc_workspace_valid",
            ),
            models.CheckConstraint(
                condition=Q(document_type__in=[value for value, _ in DocumentType.choices]),
                name="doc_type_valid",
            ),
            models.CheckConstraint(condition=Q(status=DocumentStatus.FINAL), name="doc_status_final"),
        ]
        indexes = [
            models.Index(fields=("company", "workspace", "-period_start"), name="doc_workspace_period_idx"),
            models.Index(fields=("company", "document_type", "-finalized_at"), name="doc_type_time_idx"),
            models.Index(fields=("company", "source_model", "source_id"), name="doc_source_lookup_idx"),
        ]

    def clean(self) -> None:
        self.document_number = (self.document_number or "").strip().upper()
        self.title = (self.title or "").strip()
        self.entity_reference = (self.entity_reference or "").strip().upper()
        self.entity_name = (self.entity_name or "").strip()
        self.source_model = (self.source_model or "").strip()
        self.source_reference = (self.source_reference or "").strip().upper()
        self.external_reference = (self.external_reference or "").strip().upper()
        if not self.document_number:
            raise ValidationError({"document_number": "Document number is required."})
        if not self.title:
            raise ValidationError({"title": "Document title is required."})
        if not self.source_model:
            raise ValidationError({"source_model": "Document source model is required."})
        if not isinstance(self.snapshot, dict) or not self.snapshot:
            raise ValidationError({"snapshot": "Document snapshot cannot be empty."})
        if len(self.source_fingerprint) != 64 or len(self.snapshot_fingerprint) != 64:
            raise ValidationError("Document integrity fingerprints must be SHA-256 values.")

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise NotSupportedError("Final business documents are immutable and cannot be updated.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotSupportedError("Final business documents are immutable and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.document_number} · {self.title}"
