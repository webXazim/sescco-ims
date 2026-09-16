from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_internal_finance_permission_decomposition"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="security_version",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
