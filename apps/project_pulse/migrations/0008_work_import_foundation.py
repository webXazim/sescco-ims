"""Project Pulse Work Progress U1/5: additive, backward-compatible schema.

Existing tasks keep their IDs, progress, statuses, category weights, and
expense relationships. New optional BOQ fields are initially empty.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project_pulse", "0007_commercial_forecasts"),
    ]

    operations = [
        migrations.CreateModel(
            name="PulseWorkImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(
                    choices=[("preview", "Preview"), ("applied", "Applied"), ("failed", "Failed")],
                    default="preview", max_length=12,
                )),
                ("category_count", models.PositiveIntegerField(default=0)),
                ("created_count", models.PositiveIntegerField(default=0)),
                ("updated_count", models.PositiveIntegerField(default=0)),
                ("unchanged_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("project", models.ForeignKey(
                    to="projects.project", on_delete=django.db.models.deletion.PROTECT,
                    related_name="pulse_work_imports",
                )),
                ("uploaded_by", models.ForeignKey(
                    to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT,
                    related_name="pulse_work_imports_uploaded",
                )),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddField(
            model_name="pulsetask",
            name="serial_number",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AlterField(
            model_name="pulsetask",
            name="title",
            field=models.CharField(max_length=1000),
        ),
        migrations.AddField(
            model_name="pulsetask",
            name="unit",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="pulsetask",
            name="quantity",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name="pulsetask",
            name="last_import_batch",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="last_imported_works", to="project_pulse.pulseworkimportbatch",
            ),
        ),
        migrations.AddField(
            model_name="pulsetask",
            name="import_row_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="pulsetask",
            constraint=models.UniqueConstraint(
                fields=("category", "serial_number"),
                condition=~models.Q(serial_number=""),
                name="pulse_task_category_sn_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="pulsetask",
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gte=0) | models.Q(quantity__isnull=True),
                name="pulse_task_qty_nonnegative",
            ),
        ),
        migrations.AddIndex(
            model_name="pulseworkimportbatch",
            index=models.Index(fields=("project", "sha256"), name="pulse_work_import_hash_idx"),
        ),
        migrations.AddIndex(
            model_name="pulseworkimportbatch",
            index=models.Index(fields=("project", "status"), name="pulse_work_import_state_idx"),
        ),
    ]
