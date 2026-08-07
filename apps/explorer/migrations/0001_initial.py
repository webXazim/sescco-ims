from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="SavedView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("view_type", models.CharField(choices=[("inventory", "Current inventory"), ("activity", "Stock activity"), ("low_stock", "Low stock")], max_length=24)),
                ("query_params", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_inventory_views", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("view_type", "name")},
        ),
        migrations.AddConstraint(
            model_name="savedview",
            constraint=models.UniqueConstraint(fields=("owner", "view_type", "name"), name="uniq_saved_view_name_per_owner_type"),
        ),
        migrations.AddIndex(
            model_name="savedview",
            index=models.Index(fields=["owner", "view_type"], name="saved_view_owner_type_idx"),
        ),
    ]
