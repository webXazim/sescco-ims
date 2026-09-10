import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("rental_manpower", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkerAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("trade", models.CharField(max_length=120)),
                ("rate_type", models.CharField(choices=[("hourly", "Hourly"), ("daily", "Daily"), ("monthly", "Monthly")], max_length=16)),
                ("rate", models.DecimalField(decimal_places=4, max_digits=18)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("change_type", models.CharField(choices=[("assignment", "Project assignment"), ("transfer", "Project transfer"), ("trade_change", "Trade change"), ("rate_change", "Rate change")], default="assignment", max_length=20)),
                ("reason", models.CharField(blank=True, max_length=300)),
                ("end_reason", models.CharField(blank=True, max_length=300)),
                ("end_notes", models.TextField(blank=True)),
                ("release_disposition", models.CharField(blank=True, choices=[("available", "Available"), ("inactive", "Inactive")], max_length=16)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancel_reason", models.CharField(blank=True, max_length=300)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rental_manpower_workerassignment_records",
                        to="core.company",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rental_assignments",
                        to="projects.project",
                    ),
                ),
                (
                    "worker",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assignments",
                        to="rental_manpower.rentalworker",
                    ),
                ),
            ],
            options={
                "db_table": "rental_worker_assignment",
                "ordering": ("worker_id", "effective_from", "created_at"),
            },
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.UniqueConstraint(
                condition=Q(effective_to__isnull=True, cancelled_at__isnull=True),
                fields=("company", "worker"),
                name="rntl_asg_open_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="rntl_asg_dates_chk",
            ),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(condition=Q(rate__gt=0), name="rntl_asg_rate_pos_chk"),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(condition=Q(rate_type__in=["hourly", "daily", "monthly"]), name="rntl_asg_rate_type_chk"),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(condition=Q(change_type__in=["assignment", "transfer", "trade_change", "rate_change"]), name="rntl_asg_change_type_chk"),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(condition=Q(release_disposition="") | Q(release_disposition__in=["available", "inactive"]), name="rntl_asg_release_disp_chk"),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(condition=Q(release_disposition="") | Q(effective_to__isnull=False), name="rntl_asg_release_end_chk"),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | Q(effective_to__isnull=True, release_disposition=""),
                name="rntl_asg_cancel_state_chk",
            ),
        ),
        migrations.AddConstraint(
            model_name="workerassignment",
            constraint=models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | ~Q(cancel_reason=""),
                name="rntl_asg_cancel_reason_chk",
            ),
        ),
        migrations.AddIndex(
            model_name="workerassignment",
            index=models.Index(fields=["company", "worker", "effective_from"], name="rntl_asg_worker_date_idx"),
        ),
        migrations.AddIndex(
            model_name="workerassignment",
            index=models.Index(fields=["company", "project", "effective_from"], name="rntl_asg_project_date_idx"),
        ),
        migrations.AddIndex(
            model_name="workerassignment",
            index=models.Index(fields=["company", "effective_from", "effective_to"], name="rntl_asg_dates_idx"),
        ),
    ]
