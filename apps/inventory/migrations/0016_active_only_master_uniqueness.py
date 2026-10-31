from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("inventory", "0015_create_missing_company_offices")]

    operations = [
        migrations.RemoveConstraint(model_name="supplier", name="supplier_company_identity_uniq"),
        migrations.RemoveConstraint(model_name="unit", name="unit_company_name_uniq"),
        migrations.RemoveConstraint(model_name="unit", name="unit_company_symbol_uniq"),
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(
                fields=("company", "normalized_name", "normalized_phone"),
                condition=Q(deleted_at__isnull=True),
                name="supplier_co_active_ident_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.UniqueConstraint(
                fields=("company", "normalized_name"),
                condition=Q(deleted_at__isnull=True),
                name="unit_co_active_name_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.UniqueConstraint(
                fields=("company", "normalized_symbol"),
                condition=Q(deleted_at__isnull=True),
                name="unit_co_active_symbol_uniq",
            ),
        ),
    ]
