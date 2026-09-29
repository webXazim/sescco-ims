import uuid
from django.db import migrations, models
import django.db.models.deletion
import apps.rental_manpower.models.timesheet_settings


class Migration(migrations.Migration):
    dependencies = [
        ("rental_manpower", "0009_postgres_search_query_hardening"),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalTimesheetProjectSettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("off_weekdays", models.JSONField(default=apps.rental_manpower.models.timesheet_settings.default_rental_timesheet_off_weekdays)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_records", to="core.company")),
                ("project", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="rental_timesheet_settings", to="projects.project")),
            ],
            options={
                "db_table": "rental_timesheet_project_settings",
                "ordering": ("project__code",),
            },
        ),
    ]
