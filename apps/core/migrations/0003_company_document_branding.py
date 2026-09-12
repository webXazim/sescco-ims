from django.core.validators import FileExtensionValidator
from django.db import migrations, models

import apps.core.models.settings


class Migration(migrations.Migration):
    dependencies = [("core", "0002_company_document_identity")]

    operations = [
        migrations.AddField(
            model_name="companysettings",
            name="document_logo",
            field=models.FileField(
                blank=True,
                max_length=180,
                upload_to=apps.core.models.settings.document_branding_upload_to,
                validators=[FileExtensionValidator(("png", "jpg", "jpeg", "webp")), apps.core.models.settings.validate_document_branding_size],
            ),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_letterhead",
            field=models.FileField(
                blank=True,
                max_length=180,
                upload_to=apps.core.models.settings.document_branding_upload_to,
                validators=[FileExtensionValidator(("png", "jpg", "jpeg", "webp")), apps.core.models.settings.validate_document_branding_size],
            ),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="document_watermark",
            field=models.FileField(
                blank=True,
                max_length=180,
                upload_to=apps.core.models.settings.document_branding_upload_to,
                validators=[FileExtensionValidator(("png", "jpg", "jpeg", "webp")), apps.core.models.settings.validate_document_branding_size],
            ),
        ),
    ]
