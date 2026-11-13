"""U04: weighted task progress and append-only operational update history."""
import decimal
import django.db.models.deletion
from django.db import migrations, models


def backfill_completed_tasks(apps, schema_editor):
    Task = apps.get_model("project_pulse", "PulseTask")
    Task.objects.using(schema_editor.connection.alias).filter(status="completed").update(progress_percent=100)


class Migration(migrations.Migration):
    dependencies = [
        ("project_pulse", "0002_work_categories_tasks"),
        ("accounts", "0020_project_pulse_u04_progress_authority"),
    ]

    operations = [
        migrations.AddField(
            model_name="pulseworkcategory", name="progress_weight",
            field=models.DecimalField(max_digits=8, decimal_places=2,
                default=decimal.Decimal("1.00"),
                help_text="Relative contribution to project completion (not a financial value)."),
        ),
        migrations.AddField(
            model_name="pulsetask", name="progress_weight",
            field=models.DecimalField(max_digits=8, decimal_places=2,
                default=decimal.Decimal("1.00"),
                help_text="Relative contribution within its work category (not a financial value)."),
        ),
        migrations.AddField(
            model_name="pulsetask", name="progress_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(backfill_completed_tasks, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="pulseworkcategory", constraint=models.CheckConstraint(
            condition=models.Q(progress_weight__gt=0), name="pulse_category_weight_gt_zero")),
        migrations.AddConstraint(model_name="pulsetask", constraint=models.CheckConstraint(
            condition=models.Q(progress_weight__gt=0), name="pulse_task_weight_gt_zero")),
        migrations.AddConstraint(model_name="pulsetask", constraint=models.CheckConstraint(
            condition=models.Q(progress_percent__gte=0, progress_percent__lte=100), name="pulse_task_percent_range")),
        migrations.AddConstraint(model_name="pulsetask", constraint=models.CheckConstraint(
            condition=(models.Q(status="completed", progress_percent=100) |
                      (~models.Q(status="completed") & models.Q(progress_percent__lt=100))),
            name="pulse_task_complete_percent_consistent")),
        migrations.AddConstraint(model_name="pulsetask", constraint=models.CheckConstraint(
            condition=~models.Q(status="not_started") | models.Q(progress_percent=0), name="pulse_task_not_started_zero")),
        migrations.CreateModel(
            name="PulseProgressUpdate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_percent", models.PositiveSmallIntegerField()),
                ("new_percent", models.PositiveSmallIntegerField()),
                ("previous_status", models.CharField(max_length=20, choices=[
                    ("not_started", "Not started"), ("in_progress", "In progress"),
                    ("blocked", "Blocked"), ("on_hold", "On hold"),
                    ("completed", "Completed"), ("cancelled", "Cancelled")])),
                ("new_status", models.CharField(max_length=20, choices=[
                    ("not_started", "Not started"), ("in_progress", "In progress"),
                    ("blocked", "Blocked"), ("on_hold", "On hold"),
                    ("completed", "Completed"), ("cancelled", "Cancelled")])),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("task", models.ForeignKey(to="project_pulse.pulsetask",
                    on_delete=django.db.models.deletion.PROTECT, related_name="progress_updates")),
                ("updated_by", models.ForeignKey(to="accounts.companymembership",
                    on_delete=django.db.models.deletion.PROTECT, related_name="pulse_progress_updates")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddIndex(model_name="pulseprogressupdate", index=models.Index(
            fields=["task", "-created_at"], name="pulse_progress_task_date_idx")),
    ]
