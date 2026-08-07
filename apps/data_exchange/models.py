from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.inventory.models import StockItem, StockMovement, Unit
from apps.projects.models import Project


MAX_IMPORT_SIZE = 20 * 1024 * 1024


def validate_import_size(file) -> None:
    if file and file.size > MAX_IMPORT_SIZE:
        raise ValidationError("Import workbooks must be 20 MB or smaller.")


class ImportJob(models.Model):
    class Type(models.TextChoices):
        LEGACY_CATALOG = "legacy_catalog", "Existing Excel database"
        OPENING_STOCK = "opening_stock", "Opening stock"

    class Status(models.TextChoices):
        PREVIEW = "preview", "Ready for review"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    import_type = models.CharField(max_length=32, choices=Type.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PREVIEW)
    source_file = models.FileField(
        upload_to="imports/source/%Y/%m/",
        validators=[
            FileExtensionValidator(allowed_extensions=("xlsx", "xlsm")),
            validate_import_size,
        ],
    )
    original_filename = models.CharField(max_length=255)
    project = models.ForeignKey(
        Project,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="import_jobs",
    )
    default_unit = models.ForeignKey(
        Unit,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="import_jobs",
    )
    options = models.JSONField(default=dict, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="import_jobs_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("status", "-created_at"), name="import_status_date_idx"),
            models.Index(fields=("import_type", "-created_at"), name="import_type_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_import_type_display()} · {self.original_filename}"

    @property
    def can_confirm(self) -> bool:
        if self.status != self.Status.PREVIEW:
            return False
        return self.rows.exclude(status=ImportRow.Status.ERROR).exclude(
            planned_action=ImportRow.Action.SKIP
        ).exists()


class ImportRow(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        IMPORTED = "imported", "Imported"
        SKIPPED = "skipped", "Skipped"

    class Action(models.TextChoices):
        CREATE = "create", "Create stock record"
        UPDATE = "update", "Update matching record"
        OPEN_EXISTING = "open_existing", "Add opening stock to matching record"
        CREATE_OPENING = "create_opening", "Create record and opening stock"
        CREATE_SEPARATE = "create_separate", "Create separate similar record"
        SKIP = "skip", "Skip"

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    planned_action = models.CharField(max_length=32, choices=Action.choices)
    requires_confirmation = models.BooleanField(default=False)
    raw_data = models.JSONField(default=dict)
    cleaned_data = models.JSONField(default=dict)
    message = models.TextField(blank=True)
    exact_match = models.ForeignKey(
        StockItem,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_rows_matched",
    )
    similar_match_ids = models.JSONField(default=list, blank=True)
    imported_stock_item = models.ForeignKey(
        StockItem,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_rows",
    )
    movement = models.ForeignKey(
        StockMovement,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="import_rows",
    )
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("row_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("job", "row_number"),
                name="uniq_import_job_row_number",
            )
        ]
        indexes = [
            models.Index(fields=("job", "status"), name="import_row_job_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id} · row {self.row_number} · {self.get_status_display()}"


class ExportAudit(models.Model):
    class Dataset(models.TextChoices):
        INVENTORY = "inventory", "Inventory"
        LOW_STOCK = "low_stock", "Low stock"
        ACTIVITY = "activity", "Stock activity"
        STOCK_HISTORY = "stock_history", "Stock history"
        PROJECT_INVENTORY = "project_inventory", "Project inventory"
        OPENING_TEMPLATE = "opening_template", "Opening-stock template"

    class Format(models.TextChoices):
        XLSX = "xlsx", "Excel"
        CSV = "csv", "CSV"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    dataset = models.CharField(max_length=32, choices=Dataset.choices)
    file_format = models.CharField(max_length=8, choices=Format.choices)
    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)
    sort = models.CharField(max_length=64, blank=True)
    scope_reference = models.CharField(max_length=120, blank=True)
    scope_label = models.CharField(max_length=240, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="exports_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("dataset", "-created_at"), name="export_dataset_date_idx"),
            models.Index(fields=("created_by", "-created_at"), name="export_user_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_dataset_display()} · {self.row_count} rows"
