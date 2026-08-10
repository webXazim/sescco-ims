from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.projects.models import Project

from .normalization import clean_display_text, normalize_phone, normalize_text


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024


def validate_attachment_size(file) -> None:
    if file and file.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError("Attachments must be 10 MB or smaller.")


class Unit(models.Model):
    name = models.CharField(max_length=80)
    normalized_name = models.CharField(max_length=80, unique=True, editable=False)
    symbol = models.CharField(max_length=20)
    normalized_symbol = models.CharField(max_length=20, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.symbol})"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if not normalize_text(self.name):
            errors["name"] = "Unit name is required."
        if not normalize_text(self.symbol):
            errors["symbol"] = "Unit symbol is required."
        if self.pk and not self.is_active:
            was_active = type(self).objects.filter(pk=self.pk, is_active=True).exists()
            if was_active and self.stock_items.filter(status="active").exists():
                errors["is_active"] = (
                    "Archive or change all active stock records before deactivating this unit."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = clean_display_text(self.name)
        self.symbol = clean_display_text(self.symbol)
        self.normalized_name = normalize_text(self.name)
        self.normalized_symbol = normalize_text(self.symbol)
        self.full_clean()
        return super().save(*args, **kwargs)


class Supplier(models.Model):
    name = models.CharField(max_length=180)
    normalized_name = models.CharField(max_length=180, editable=False)
    phone = models.CharField(max_length=40)
    normalized_phone = models.CharField(max_length=40, editable=False)
    location = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "phone")
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_name", "normalized_phone"),
                name="uniq_supplier_identity",
            )
        ]
        indexes = [
            models.Index(fields=("normalized_name",), name="supplier_name_norm_idx"),
            models.Index(fields=("normalized_phone",), name="supplier_phone_norm_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} · {self.phone}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if not normalize_text(self.name):
            errors["name"] = "Supplier name is required."
        if not normalize_phone(self.phone):
            errors["phone"] = "Supplier phone is required."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = clean_display_text(self.name)
        self.phone = clean_display_text(self.phone)
        self.location = clean_display_text(self.location)
        self.notes = (self.notes or "").strip()
        self.normalized_name = normalize_text(self.name)
        self.normalized_phone = normalize_phone(self.phone)
        self.full_clean()
        return super().save(*args, **kwargs)


class StockItem(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="stock_items")
    material_name = models.CharField(max_length=180)
    normalized_material_name = models.CharField(max_length=180, editable=False)
    description = models.TextField(blank=True)
    supplier_name = models.CharField(max_length=180)
    normalized_supplier_name = models.CharField(max_length=180, editable=False)
    supplier_phone = models.CharField(max_length=40)
    normalized_supplier_phone = models.CharField(max_length=40, editable=False)
    supplier_location = models.CharField(max_length=180, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="stock_items")
    current_quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    minimum_quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    latest_unit_price = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        blank=True,
        null=True,
    )
    latest_addition_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_items_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_items_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    PROTECTED_BALANCE_FIELDS = (
        "current_quantity",
        "latest_unit_price",
        "latest_addition_date",
    )

    class Meta:
        ordering = ("project", "material_name", "supplier_name")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "project",
                    "normalized_material_name",
                    "normalized_supplier_name",
                    "normalized_supplier_phone",
                ),
                name="uniq_stock_identity_per_project",
            ),
            models.CheckConstraint(
                condition=Q(current_quantity__gte=0),
                name="stock_current_quantity_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(minimum_quantity__gte=0),
                name="stock_minimum_quantity_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("project", "status", "material_name"),
                name="stock_project_status_name_idx",
            ),
            models.Index(
                fields=("normalized_supplier_name", "normalized_supplier_phone"),
                name="stock_supplier_identity_idx",
            ),
            models.Index(fields=("latest_addition_date",), name="stock_latest_add_date_idx"),
            models.Index(fields=("normalized_material_name",), name="stock_material_norm_idx"),
            models.Index(fields=("current_quantity",), name="stock_quantity_idx"),
            models.Index(fields=("latest_unit_price",), name="stock_latest_price_idx"),
            models.Index(fields=("updated_at",), name="stock_updated_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.project.code} · {self.material_name} · {self.supplier_name}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.current_quantity is not None and self.current_quantity < 0:
            errors["current_quantity"] = "Current quantity cannot be negative."
        if self.minimum_quantity is not None and self.minimum_quantity < 0:
            errors["minimum_quantity"] = "Minimum quantity cannot be negative."
        original_project_id = None
        original_unit_id = None
        original_status = None
        has_movements = False
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values(
                "project_id",
                "unit_id",
                "status",
            ).first()
            if original:
                original_project_id = original["project_id"]
                original_unit_id = original["unit_id"]
                original_status = original["status"]
                has_movements = self.movements.exists()

        if has_movements and self.project_id != original_project_id:
            errors["project"] = "Project is locked after the first stock movement."
        if has_movements and self.unit_id != original_unit_id:
            errors["unit"] = "Unit is locked after the first stock movement."
        if (
            self.status == self.Status.ARCHIVED
            and original_status != self.Status.ARCHIVED
            and self.current_quantity != 0
        ):
            errors["status"] = "A stock record can be archived only at zero balance."
        if self.status == self.Status.ACTIVE and original_status == self.Status.ARCHIVED:
            if self.project_id and not Project.objects.filter(
                pk=self.project_id, status=Project.Status.ACTIVE
            ).exists():
                errors["status"] = "Reactivate the project before this stock record."
            if self.unit_id and not Unit.objects.filter(
                pk=self.unit_id, is_active=True
            ).exists():
                errors["status"] = "Reactivate the unit before this stock record."

        project_is_active = (
            self.project_id
            and Project.objects.filter(
                pk=self.project_id,
                status=Project.Status.ACTIVE,
            ).exists()
        )
        if self.project_id and not project_is_active and (
            self._state.adding or self.project_id != original_project_id
        ):
            errors["project"] = (
                "New stock records and project changes require an active project."
            )

        unit_is_active = (
            self.unit_id
            and Unit.objects.filter(pk=self.unit_id, is_active=True).exists()
        )
        if self.unit_id and not unit_is_active and (
            self._state.adding or self.unit_id != original_unit_id
        ):
            errors["unit"] = "New stock records and unit changes require an active unit."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        inventory_service = kwargs.pop("_inventory_service", False)
        self.material_name = clean_display_text(self.material_name)
        self.description = (self.description or "").strip()
        self.supplier_name = clean_display_text(self.supplier_name)
        self.supplier_phone = clean_display_text(self.supplier_phone)
        self.supplier_location = clean_display_text(self.supplier_location)
        self.normalized_material_name = normalize_text(self.material_name)
        self.normalized_supplier_name = normalize_text(self.supplier_name)
        self.normalized_supplier_phone = normalize_phone(self.supplier_phone)

        if self._state.adding and not inventory_service:
            if self.current_quantity not in (None, Decimal("0")):
                raise ValidationError(
                    {
                        "current_quantity": (
                            "Opening quantity must be created through a stock movement."
                        )
                    }
                )
            if self.latest_unit_price is not None or self.latest_addition_date is not None:
                raise ValidationError(
                    "Latest purchase fields are controlled by the inventory service."
                )
        elif self.pk and not inventory_service:
            original = type(self).objects.filter(pk=self.pk).values(
                *self.PROTECTED_BALANCE_FIELDS
            ).first()
            if original:
                changed = [
                    field
                    for field in self.PROTECTED_BALANCE_FIELDS
                    if getattr(self, field) != original[field]
                ]
                if changed:
                    raise ValidationError(
                        "Current quantity and latest purchase values can only change through "
                        "a stock movement."
                    )

        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def stock_status(self) -> str:
        if self.current_quantity <= 0:
            return "out"
        if self.minimum_quantity > 0 and self.current_quantity <= self.minimum_quantity:
            return "low"
        return "in"

    @property
    def stock_status_label(self) -> str:
        return {"out": "Out of stock", "low": "Low stock", "in": "In stock"}[
            self.stock_status
        ]

    @property
    def quantity_display(self) -> str:
        quantity = f"{self.current_quantity:f}".rstrip("0").rstrip(".") or "0"
        return f"{quantity} {self.unit.symbol}"


class StockDocument(models.Model):
    """An immutable supporting document attached to a stock record."""

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    file = models.FileField(
        upload_to="stock-records/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=("pdf", "jpg", "jpeg", "png")),
            validate_attachment_size,
        ],
    )
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return f"{self.stock_item} · {self.original_name}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Stock documents are immutable and cannot be edited.")
        self.original_name = self.original_name.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock documents are immutable and cannot be deleted.")


class StockMovement(models.Model):
    class Type(models.TextChoices):
        OPENING = "opening", "Opening stock"
        ADDITION = "addition", "Stock added"
        USAGE = "usage", "Stock used"
        ADJUSTMENT_IN = "adjustment_in", "Positive adjustment"
        ADJUSTMENT_OUT = "adjustment_out", "Negative adjustment"
        REVERSAL = "reversal", "Reversal"

    INBOUND_TYPES = {Type.OPENING, Type.ADDITION, Type.ADJUSTMENT_IN}
    OUTBOUND_TYPES = {Type.USAGE, Type.ADJUSTMENT_OUT}

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    idempotency_key = models.UUIDField(unique=True, editable=False)
    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    movement_type = models.CharField(max_length=24, choices=Type.choices)
    project_code_snapshot = models.CharField(max_length=30, blank=True, default="", editable=False)
    project_name_snapshot = models.CharField(max_length=180, blank=True, default="", editable=False)
    material_name_snapshot = models.CharField(
        max_length=180, blank=True, default="", editable=False
    )
    supplier_name_snapshot = models.CharField(
        max_length=180, blank=True, default="", editable=False
    )
    supplier_phone_snapshot = models.CharField(
        max_length=40, blank=True, default="", editable=False
    )
    supplier_phone_normalized_snapshot = models.CharField(
        max_length=40, blank=True, default="", editable=False
    )
    unit_symbol_snapshot = models.CharField(max_length=20, blank=True, default="", editable=False)
    quantity = models.DecimalField(
        max_digits=16,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    previous_balance = models.DecimalField(max_digits=16, decimal_places=3)
    new_balance = models.DecimalField(max_digits=16, decimal_places=3)
    unit_price = models.DecimalField(max_digits=16, decimal_places=2, blank=True, null=True)
    movement_date = models.DateField()
    invoice_reference = models.CharField(max_length=120, blank=True)
    purpose = models.CharField(max_length=180, blank=True)
    recipient = models.CharField(max_length=180, blank=True)
    reason = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to="stock-movements/%Y/%m/",
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=("pdf", "jpg", "jpeg", "png")),
            validate_attachment_size,
        ],
    )
    reversal_of = models.OneToOneField(
        "self",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-movement_date", "-created_at", "-pk")
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="movement_quantity_positive"),
            models.CheckConstraint(
                condition=Q(previous_balance__gte=0),
                name="movement_previous_balance_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(new_balance__gte=0),
                name="movement_new_balance_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__isnull=True) | Q(unit_price__gte=0),
                name="movement_unit_price_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=("stock_item", "-movement_date", "-created_at"),
                name="movement_item_date_idx",
            ),
            models.Index(
                fields=("movement_type", "-movement_date"),
                name="movement_type_date_idx",
            ),
            models.Index(fields=("invoice_reference",), name="movement_reference_idx"),
            models.Index(fields=("created_by", "-movement_date"), name="movement_user_date_idx"),
            models.Index(fields=("unit_price",), name="movement_unit_price_idx"),
            models.Index(fields=("project_code_snapshot",), name="movement_project_snap_idx"),
        ]

    def __str__(self) -> str:
        identity = self.material_name_snapshot or self.stock_item.material_name
        project = self.project_code_snapshot or self.stock_item.project.code
        return f"{project} · {identity} · {self.get_movement_type_display()} · {self.quantity}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.quantity is not None and self.quantity <= 0:
            errors["quantity"] = "Movement quantity must be greater than zero."
        if self.previous_balance is not None and self.previous_balance < 0:
            errors["previous_balance"] = "Previous balance cannot be negative."
        if self.new_balance is not None and self.new_balance < 0:
            errors["new_balance"] = "New balance cannot be negative."
        if self.movement_type == self.Type.REVERSAL and not self.reversal_of_id:
            errors["reversal_of"] = "A reversal must reference the original movement."
        if self.movement_type != self.Type.REVERSAL and self.reversal_of_id:
            errors["reversal_of"] = "Only reversal movements can reference another movement."
        if self.reversal_of_id and self.reversal_of_id == self.pk:
            errors["reversal_of"] = "A movement cannot reverse itself."

        if (
            self.quantity is not None
            and self.previous_balance is not None
            and self.new_balance is not None
        ):
            if self.movement_type in self.INBOUND_TYPES:
                expected = self.previous_balance + self.quantity
                if self.new_balance != expected:
                    errors["new_balance"] = "Inbound movement balance does not reconcile."
            elif self.movement_type in self.OUTBOUND_TYPES:
                expected = self.previous_balance - self.quantity
                if self.new_balance != expected:
                    errors["new_balance"] = "Outbound movement balance does not reconcile."
            elif self.movement_type == self.Type.REVERSAL and self.reversal_of_id:
                original = self.reversal_of
                if original.stock_item_id != self.stock_item_id:
                    errors["stock_item"] = "A reversal must use the original stock record."
                if self.quantity != original.quantity:
                    errors["quantity"] = "A reversal must use the original quantity."
                original_delta = original.new_balance - original.previous_balance
                expected = self.previous_balance - original_delta
                if self.new_balance != expected:
                    errors["new_balance"] = "Reversal balance does not reconcile."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Stock movements are immutable and cannot be edited.")
        if self.stock_item_id:
            if self.reversal_of_id:
                source = self.reversal_of
                self.project_code_snapshot = source.project_code_display
                self.project_name_snapshot = source.project_name_display
                self.material_name_snapshot = source.material_name_display
                self.supplier_name_snapshot = source.supplier_name_display
                self.supplier_phone_snapshot = source.supplier_phone_display
                self.unit_symbol_snapshot = source.unit_symbol_display
            else:
                item = self.stock_item
                self.project_code_snapshot = item.project.code
                self.project_name_snapshot = item.project.name
                self.material_name_snapshot = item.material_name
                self.supplier_name_snapshot = item.supplier_name
                self.supplier_phone_snapshot = item.supplier_phone
                self.unit_symbol_snapshot = item.unit.symbol
            self.supplier_phone_normalized_snapshot = normalize_phone(
                self.supplier_phone_snapshot
            )
        self.invoice_reference = clean_display_text(self.invoice_reference)
        self.purpose = clean_display_text(self.purpose)
        self.recipient = clean_display_text(self.recipient)
        self.reason = clean_display_text(self.reason)
        self.notes = (self.notes or "").strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements are immutable and cannot be deleted.")

    @property
    def is_reversed(self) -> bool:
        return hasattr(self, "reversal")

    @property
    def is_inbound(self) -> bool:
        if self.movement_type == self.Type.REVERSAL and self.reversal_of_id:
            return self.new_balance > self.previous_balance
        return self.movement_type in self.INBOUND_TYPES

    @property
    def signed_quantity(self) -> Decimal:
        return self.quantity if self.is_inbound else -self.quantity

    @property
    def project_code_display(self) -> str:
        return self.project_code_snapshot or self.stock_item.project.code

    @property
    def project_name_display(self) -> str:
        return self.project_name_snapshot or self.stock_item.project.name

    @property
    def material_name_display(self) -> str:
        return self.material_name_snapshot or self.stock_item.material_name

    @property
    def supplier_name_display(self) -> str:
        return self.supplier_name_snapshot or self.stock_item.supplier_name

    @property
    def supplier_phone_display(self) -> str:
        return self.supplier_phone_snapshot or self.stock_item.supplier_phone

    @property
    def unit_symbol_display(self) -> str:
        return self.unit_symbol_snapshot or self.stock_item.unit.symbol

    @property
    def signed_quantity_display(self) -> str:
        sign = "+" if self.is_inbound else "−"
        quantity = f"{self.quantity:f}".rstrip("0").rstrip(".")
        return f"{sign}{quantity} {self.unit_symbol_display}"
