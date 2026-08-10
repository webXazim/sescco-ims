from django.db import migrations


def add_stock_value_column(apps, schema_editor):
    table_preference = apps.get_model("explorer", "TablePreference")
    for preference in table_preference.objects.filter(
        view_type__in=("inventory", "low_stock")
    ):
        columns = list(preference.columns or [])
        if "price" in columns and "value" not in columns:
            columns.insert(columns.index("price") + 1, "value")
            preference.columns = columns
            preference.save(update_fields=("columns",))


def remove_stock_value_column(apps, schema_editor):
    table_preference = apps.get_model("explorer", "TablePreference")
    for preference in table_preference.objects.filter(
        view_type__in=("inventory", "low_stock")
    ):
        columns = [column for column in (preference.columns or []) if column != "value"]
        preference.columns = columns
        preference.save(update_fields=("columns",))


class Migration(migrations.Migration):
    dependencies = [("explorer", "0002_tablepreference")]

    operations = [
        migrations.RunPython(add_stock_value_column, remove_stock_value_column),
    ]
