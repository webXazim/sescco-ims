"""Company-level classification tags for all three sourcing provider types."""
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("sourcing", "0012_subcontractor_qualification_documents")]
    operations = [
        migrations.AddField(model_name="sourcingvendor", name="tags", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="sourcingmanpowersupplier", name="tags", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="sourcingsubcontractor", name="tags", field=models.JSONField(blank=True, default=list)),
    ]
