from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("projects", "0006_project_reversible_archive_state"), ("accounts", "0016_project_manager_approval"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.AddField(
        model_name="project", name="inventory_manager",
        field=models.ForeignKey(
            to=settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name="managed_inventory_projects",
            help_text="Assigned Project Manager who approves incoming and outgoing inventory requests.",
        ),
    )]
