from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0001_platform_core")]

    operations = [
        migrations.AddField(
            model_name="companysettings",
            name="commercial_registration",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="vat_number",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_address",
            field=models.CharField(blank=True, max_length=400),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_phone",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="website",
            field=models.URLField(blank=True, max_length=300),
        ),
    ]
