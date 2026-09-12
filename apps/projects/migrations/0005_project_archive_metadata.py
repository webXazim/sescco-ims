from django.db import migrations, models


def backfill_project_archive_metadata(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    for project in Project.objects.filter(status="archived", archived_at__isnull=True).iterator():
        Project.objects.filter(pk=project.pk).update(
            archived_at=project.updated_at,
            archived_reason="Migrated from the existing archived project state.",
        )


class Migration(migrations.Migration):
    dependencies = [("projects", "0004_shared_project_authority")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="archived_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(backfill_project_archive_metadata, migrations.RunPython.noop),
    ]
