from django.core.validators import FileExtensionValidator
from django.db import migrations, models

import apps.core.models.settings


BRANDING_MODE_COLUMN = "document_branding_mode"
BRANDING_FILE_COLUMNS = ("document_logo", "document_letterhead", "document_watermark")


def _table_columns(schema_editor, table_name: str) -> set[str]:
    with schema_editor.connection.cursor() as cursor:
        return {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }


def _repair_database_schema(apps, schema_editor) -> None:
    """Repair databases that recorded old core.0003 before branding-mode existed.

    core.0003 shipped in production with the three branding file fields. A later
    source package accidentally rewrote that already-applied migration to also
    contain document_branding_mode. Migration history therefore said 0003 was
    applied while older live databases legitimately lacked that newer column.

    The repair is deliberately idempotent so it also works for databases created
    from the accidentally rewritten 0003: existing columns are left intact.
    """

    CompanySettings = apps.get_model("core", "CompanySettings")
    table_name = CompanySettings._meta.db_table
    columns = _table_columns(schema_editor, table_name)

    if BRANDING_MODE_COLUMN not in columns:
        mode_field = models.CharField(
            choices=[("standard", "Standard header"), ("letterhead", "Full-page letterhead")],
            default="standard",
            max_length=16,
        )
        mode_field.set_attributes_from_name(BRANDING_MODE_COLUMN)
        mode_field.model = CompanySettings
        schema_editor.add_field(CompanySettings, mode_field)
        columns.add(BRANDING_MODE_COLUMN)

    # PostgreSQL enforces varchar length. The original immutable 0003 used 180,
    # while the accidentally rewritten source used FileField's default 100.
    # Widening to 180 is safe and preserves both lineages. SQLite does not enforce
    # varchar length, so no physical repair is needed there.
    if schema_editor.connection.vendor == "postgresql":
        qn = schema_editor.quote_name
        for column_name in BRANDING_FILE_COLUMNS:
            if column_name in columns:
                schema_editor.execute(
                    f"ALTER TABLE {qn(table_name)} "
                    f"ALTER COLUMN {qn(column_name)} TYPE varchar(180)"
                )


class Migration(migrations.Migration):
    dependencies = [("core", "0003_company_document_branding")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(_repair_database_schema, migrations.RunPython.noop)],
            state_operations=[
                migrations.AddField(
                    model_name="companysettings",
                    name="document_branding_mode",
                    field=models.CharField(
                        choices=[("standard", "Standard header"), ("letterhead", "Full-page letterhead")],
                        default="standard",
                        max_length=16,
                    ),
                ),
                migrations.AlterField(
                    model_name="companysettings",
                    name="document_logo",
                    field=models.FileField(
                        blank=True,
                        max_length=180,
                        upload_to=apps.core.models.settings.company_logo_upload_to,
                        validators=[
                            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"]),
                            apps.core.models.settings.validate_document_branding_size,
                        ],
                    ),
                ),
                migrations.AlterField(
                    model_name="companysettings",
                    name="document_letterhead",
                    field=models.FileField(
                        blank=True,
                        max_length=180,
                        upload_to=apps.core.models.settings.company_letterhead_upload_to,
                        validators=[
                            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"]),
                            apps.core.models.settings.validate_document_branding_size,
                        ],
                    ),
                ),
                migrations.AlterField(
                    model_name="companysettings",
                    name="document_watermark",
                    field=models.FileField(
                        blank=True,
                        max_length=180,
                        upload_to=apps.core.models.settings.company_watermark_upload_to,
                        validators=[
                            FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"]),
                            apps.core.models.settings.validate_document_branding_size,
                        ],
                    ),
                ),
            ],
        ),
    ]
