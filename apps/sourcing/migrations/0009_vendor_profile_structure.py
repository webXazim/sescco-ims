from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0008_align_abstract_relation_state"),
    ]

    operations = [
        migrations.RenameField(
            model_name="sourcingvendor",
            old_name="phone",
            new_name="company_phone",
        ),
        migrations.AddField(
            model_name="sourcingvendor",
            name="company_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="sourcingvendor",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="sourcingvendor",
            name="street_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="sourcingvendor",
            name="district",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="sourcingvendor",
            name="postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
