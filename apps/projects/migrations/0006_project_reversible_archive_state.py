from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0005_project_archive_metadata")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="archive_previous_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("active", "Active"),
                    ("on_hold", "On Hold"),
                    ("completed", "Completed"),
                    ("archived", "Archived"),
                ],
                editable=False,
                help_text="Status preserved when the project is archived so restore is exact.",
                max_length=20,
            ),
        ),
    ]
