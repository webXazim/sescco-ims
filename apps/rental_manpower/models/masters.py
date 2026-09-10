from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import CompanyOwnedModel


class SupplierStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"



class RentalWorkerStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class ManpowerSupplier(CompanyOwnedModel):
    """Permanent manpower-supplier master used by rental workforce operations."""

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=SupplierStatus.choices,
        default=SupplierStatus.ACTIVE,
        db_index=True,
    )
    contact_person = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    cr_number = models.CharField(max_length=60, blank=True)
    vat_number = models.CharField(max_length=60, blank=True)
    payment_terms = models.CharField(max_length=160, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "rental_manpower_supplier"
        ordering = ("code", "name")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="rntl_sup_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="rntl_sup_name_uniq"),
            models.UniqueConstraint(
                fields=("company", "cr_number"),
                condition=~Q(cr_number=""),
                name="rntl_sup_cr_uniq",
            ),
            models.UniqueConstraint(
                fields=("company", "vat_number"),
                condition=~Q(vat_number=""),
                name="rntl_sup_vat_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SupplierStatus.choices]),
                name="rntl_sup_status_chk",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "name"), name="rntl_sup_status_name_idx"),
        ]

    def clean(self) -> None:
        self.code = (self.code or "").strip().upper()
        self.name = (self.name or "").strip()
        self.contact_person = (self.contact_person or "").strip()
        self.phone = (self.phone or "").strip()
        self.email = (self.email or "").strip().lower()
        self.cr_number = (self.cr_number or "").strip().upper()
        self.vat_number = (self.vat_number or "").strip().upper()
        self.payment_terms = (self.payment_terms or "").strip()
        self.address = (self.address or "").strip()
        self.notes = (self.notes or "").strip()
        if not self.code:
            raise ValidationError({"code": "Supplier code is required."})
        if not self.name:
            raise ValidationError({"name": "Supplier name is required."})

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"



class RentalWorker(CompanyOwnedModel):
    """Permanent rental-worker identity linked to one managed manpower supplier.

    Project, trade and rate are intentionally not stored here. The assignment domain owns their effective-dated
    assignment history so transfers never overwrite the permanent worker master.
    """

    worker_number = models.CharField(max_length=40)
    full_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    supplier = models.ForeignKey(
        ManpowerSupplier,
        on_delete=models.PROTECT,
        related_name="workers",
    )
    status = models.CharField(
        max_length=20,
        choices=RentalWorkerStatus.choices,
        default=RentalWorkerStatus.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "rental_worker"
        ordering = ("worker_number", "full_name")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "worker_number"),
                name="rntl_wrk_number_uniq",
            ),
            models.UniqueConstraint(
                fields=("company", "national_id"),
                condition=~Q(national_id=""),
                name="rntl_wrk_national_id_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in RentalWorkerStatus.choices]),
                name="rntl_wrk_status_chk",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "full_name"), name="rntl_wrk_status_name_idx"),
            models.Index(fields=("company", "supplier", "status"), name="rntl_wrk_supplier_status_idx"),
        ]

    def clean(self) -> None:
        self.worker_number = (self.worker_number or "").strip().upper()
        self.full_name = (self.full_name or "").strip()
        self.national_id = (self.national_id or "").strip()
        self.phone = (self.phone or "").strip()
        self.notes = (self.notes or "").strip()
        if not self.worker_number:
            raise ValidationError({"worker_number": "Worker number is required."})
        if not self.full_name:
            raise ValidationError({"full_name": "Worker name is required."})
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            raise ValidationError({"supplier": "Supplier must belong to the same company."})
        if self.supplier_id and self.status == RentalWorkerStatus.ACTIVE and self.supplier.status != SupplierStatus.ACTIVE:
            raise ValidationError({"supplier": "Active workers must belong to an active supplier."})

    def __str__(self) -> str:
        return f"{self.worker_number} · {self.full_name}"
