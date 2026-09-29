import uuid
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import apps.rental_manpower.models.timesheet_settings


def backfill_period_policies(apps, schema_editor):
    ProjectSettings = apps.get_model("rental_manpower", "RentalTimesheetProjectSettings")
    Period = apps.get_model("rental_manpower", "RentalTimesheetPeriod")
    PeriodPolicy = apps.get_model("rental_manpower", "RentalTimesheetPeriodPolicy")

    settings_by_project = {
        row.project_id: row
        for row in ProjectSettings.objects.all().only(
            "project_id", "off_weekdays", "regular_hours_per_day", "overtime_multiplier", "automatic_overtime"
        )
    }
    batch = []
    existing = set(PeriodPolicy.objects.values_list("period_id", flat=True))
    for period in Period.objects.all().only("id", "company_id", "project_id", "status"):
        if period.id in existing:
            continue
        source = settings_by_project.get(period.project_id)
        batch.append(
            PeriodPolicy(
                company_id=period.company_id,
                period_id=period.id,
                off_weekdays=list(getattr(source, "off_weekdays", None) or ["fri", "sat"]),
                regular_hours_per_day=getattr(source, "regular_hours_per_day", None) or Decimal("10.00"),
                overtime_multiplier=getattr(source, "overtime_multiplier", None) or Decimal("1.0000"),
                # Preserve pre-upgrade financial meaning for protected historical periods:
                # before this release all numeric daily hours were regular hours. Draft
                # periods are still editable and adopt the new project default immediately.
                automatic_overtime=(period.status == "draft"),
            )
        )
        if len(batch) >= 1000:
            PeriodPolicy.objects.bulk_create(batch, batch_size=1000)
            batch.clear()
    if batch:
        PeriodPolicy.objects.bulk_create(batch, batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("rental_manpower", "0010_rental_timesheet_project_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentaltimesheetprojectsettings",
            name="automatic_overtime",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="rentaltimesheetprojectsettings",
            name="overtime_multiplier",
            field=models.DecimalField(decimal_places=4, default=Decimal("1.0000"), max_digits=6),
        ),
        migrations.AddField(
            model_name="rentaltimesheetprojectsettings",
            name="regular_hours_per_day",
            field=models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=5),
        ),
        migrations.CreateModel(
            name="RentalTimesheetPeriodPolicy",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("off_weekdays", models.JSONField(default=apps.rental_manpower.models.timesheet_settings.default_rental_timesheet_off_weekdays)),
                ("regular_hours_per_day", models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=5)),
                ("overtime_multiplier", models.DecimalField(decimal_places=4, default=Decimal("1.0000"), max_digits=6)),
                ("automatic_overtime", models.BooleanField(default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_records", to="core.company")),
                ("period", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="policy_snapshot", to="rental_manpower.rentaltimesheetperiod")),
            ],
            options={
                "db_table": "rental_timesheet_period_policy",
                "ordering": ("-period__period_start", "period__project__code"),
            },
        ),
        migrations.RunPython(backfill_period_policies, migrations.RunPython.noop),
    ]
