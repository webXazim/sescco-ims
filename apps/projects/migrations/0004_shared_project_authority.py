import uuid

from django.db import migrations, models
from django.db.models import F, Q


def backfill_project_references(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    # Do not use one migration default for all existing rows: every project needs its own
    # stable public UUID while the existing integer PK remains the database/FK authority.
    for project in Project.objects.filter(reference__isnull=True).only("pk").iterator(chunk_size=500):
        Project.objects.filter(pk=project.pk, reference__isnull=True).update(reference=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0003_company_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="reference",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_project_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="reference",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="project",
            name="end_date",
            field=models.DateField(
                blank=True,
                help_text="Actual project end date. Required when a project is newly completed.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="manager_name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AlterField(
            model_name="project",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("on_hold", "On Hold"),
                    ("completed", "Completed"),
                    ("archived", "Archived"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["company", "start_date"], name="project_company_start_idx"),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="project_end_after_start_chk",
            ),
        ),
    ]
