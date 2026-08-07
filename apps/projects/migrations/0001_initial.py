import apps.projects.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        help_text="Short project tag shown across inventory, for example ARAMCO-01.",
                        max_length=30,
                        unique=True,
                        validators=[apps.projects.models.project_code_validator],
                    ),
                ),
                ("name", models.CharField(max_length=180)),
                ("client_name", models.CharField(blank=True, max_length=180)),
                ("location", models.CharField(blank=True, max_length=180)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("expected_completion_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("completed", "Completed"),
                            ("archived", "Archived"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="projects_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="projects_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("code",),
                "indexes": [
                    models.Index(
                        fields=["status", "code"],
                        name="project_status_code_idx",
                    ),
                    models.Index(fields=["name"], name="project_name_idx"),
                ],
            },
        )
    ]
