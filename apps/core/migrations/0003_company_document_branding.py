from django.db import migrations, models
import django.core.validators
import apps.core.models.settings


class Migration(migrations.Migration):
    dependencies = [("core", "0002_company_document_identity")]

    operations = [
        migrations.AddField(
            model_name="companysettings",
            name="document_branding_mode",
            field=models.CharField(
                choices=[("standard", "Standard header"), ("letterhead", "Full-page letterhead")],
                default="standard",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_logo",
            field=models.FileField(
                blank=True,
                upload_to=apps.core.models.settings.company_logo_upload_to,
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])],
            ),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_letterhead",
            field=models.FileField(
                blank=True,
                upload_to=apps.core.models.settings.company_letterhead_upload_to,
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])],
            ),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_watermark",
            field=models.FileField(
                blank=True,
                upload_to=apps.core.models.settings.company_watermark_upload_to,
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])],
            ),
        ),
    ]
