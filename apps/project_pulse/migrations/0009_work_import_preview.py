"""Add temporary normalized Excel preview data; keep existing import history intact."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("project_pulse", "0008_work_import_foundation")]
    operations = [
        migrations.AddField(
            model_name="pulseworkimportbatch", name="preview_data",
            field=models.JSONField(default=dict, blank=True),
        ),
        migrations.AddField(
            model_name="pulseworkimportbatch", name="preview_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
