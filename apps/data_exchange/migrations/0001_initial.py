# Generated for Upgrade 6.

import django.core.validators
import django.db.models.deletion
import apps.data_exchange.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0005_explorer_indexes"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("import_type", models.CharField(choices=[("legacy_catalog", "Existing Excel database"), ("opening_stock", "Opening stock")], max_length=32)),
                ("status", models.CharField(choices=[("preview", "Ready for review"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="preview", max_length=24)),
                ("source_file", models.FileField(upload_to="imports/source/%Y/%m/", validators=[django.core.validators.FileExtensionValidator(allowed_extensions=("xlsx", "xlsm")), apps.data_exchange.models.validate_import_size])),
                ("original_filename", models.CharField(max_length=255)),
                ("options", models.JSONField(blank=True, default=dict)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("valid_rows", models.PositiveIntegerField(default=0)),
                ("warning_rows", models.PositiveIntegerField(default=0)),
                ("error_rows", models.PositiveIntegerField(default=0)),
                ("imported_rows", models.PositiveIntegerField(default=0)),
                ("skipped_rows", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="import_jobs_created", to=settings.AUTH_USER_MODEL)),
                ("default_unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_jobs", to="inventory.unit")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="import_jobs", to="projects.project")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.CreateModel(
            name="ExportAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("dataset", models.CharField(choices=[("inventory", "Inventory"), ("low_stock", "Low stock"), ("activity", "Stock activity"), ("stock_history", "Stock history"), ("project_inventory", "Project inventory"), ("opening_template", "Opening-stock template")], max_length=32)),
                ("file_format", models.CharField(choices=[("xlsx", "Excel"), ("csv", "CSV")], max_length=8)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("columns", models.JSONField(blank=True, default=list)),
                ("sort", models.CharField(blank=True, max_length=64)),
                ("scope_reference", models.CharField(blank=True, max_length=120)),
                ("scope_label", models.CharField(blank=True, max_length=240)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="exports_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.CreateModel(
            name="ImportRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("valid", "Valid"), ("warning", "Warning"), ("error", "Error"), ("imported", "Imported"), ("skipped", "Skipped")], max_length=20)),
                ("planned_action", models.CharField(choices=[("create", "Create stock record"), ("update", "Update matching record"), ("open_existing", "Add opening stock to matching record"), ("create_opening", "Create record and opening stock"), ("create_separate", "Create separate similar record"), ("skip", "Skip")], max_length=32)),
                ("requires_confirmation", models.BooleanField(default=False)),
                ("raw_data", models.JSONField(default=dict)),
                ("cleaned_data", models.JSONField(default=dict)),
                ("message", models.TextField(blank=True)),
                ("similar_match_ids", models.JSONField(blank=True, default=list)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("exact_match", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="import_rows_matched", to="inventory.stockitem")),
                ("imported_stock_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="import_rows", to="inventory.stockitem")),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="data_exchange.importjob")),
                ("movement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="import_rows", to="inventory.stockmovement")),
            ],
            options={"ordering": ("row_number",)},
        ),
        migrations.AddConstraint(
            model_name="importrow",
            constraint=models.UniqueConstraint(fields=("job", "row_number"), name="uniq_import_job_row_number"),
        ),
        migrations.AddIndex(model_name="importjob", index=models.Index(fields=["status", "-created_at"], name="import_status_date_idx")),
        migrations.AddIndex(model_name="importjob", index=models.Index(fields=["import_type", "-created_at"], name="import_type_date_idx")),
        migrations.AddIndex(model_name="importrow", index=models.Index(fields=["job", "status"], name="import_row_job_status_idx")),
        migrations.AddIndex(model_name="exportaudit", index=models.Index(fields=["dataset", "-created_at"], name="export_dataset_date_idx")),
        migrations.AddIndex(model_name="exportaudit", index=models.Index(fields=["created_by", "-created_at"], name="export_user_date_idx")),
    ]
