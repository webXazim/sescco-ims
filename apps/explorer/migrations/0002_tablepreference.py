from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("explorer", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="savedview",
            name="query_params",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="TablePreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("view_type", models.CharField(choices=[("inventory", "Current inventory"), ("activity", "Stock activity"), ("low_stock", "Low stock")], max_length=24)),
                ("columns", models.JSONField(default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_table_preferences", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("owner", "view_type")},
        ),
        migrations.AddConstraint(
            model_name="tablepreference",
            constraint=models.UniqueConstraint(fields=("owner", "view_type"), name="uniq_table_preference_owner_view"),
        ),
    ]
