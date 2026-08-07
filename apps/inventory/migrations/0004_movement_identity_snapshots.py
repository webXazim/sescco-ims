import re
import unicodedata

from django.db import migrations, models


def populate_movement_snapshots(apps, schema_editor):
    StockMovement = apps.get_model("inventory", "StockMovement")
    queryset = StockMovement.objects.select_related("stock_item__project", "stock_item__unit")
    batch = []
    for movement in queryset.iterator(chunk_size=500):
        item = movement.stock_item
        movement.project_code_snapshot = item.project.code
        movement.project_name_snapshot = item.project.name
        movement.material_name_snapshot = item.material_name
        movement.supplier_name_snapshot = item.supplier_name
        movement.supplier_phone_snapshot = item.supplier_phone
        raw_phone = unicodedata.normalize("NFKC", item.supplier_phone or "")
        digits = re.sub(r"\D+", "", raw_phone)
        if digits.startswith("00"):
            digits = digits[2:]
        movement.supplier_phone_normalized_snapshot = digits
        movement.unit_symbol_snapshot = item.unit.symbol
        batch.append(movement)
        if len(batch) >= 500:
            StockMovement.objects.bulk_update(
                batch,
                [
                    "project_code_snapshot",
                    "project_name_snapshot",
                    "material_name_snapshot",
                    "supplier_name_snapshot",
                    "supplier_phone_snapshot",
                    "supplier_phone_normalized_snapshot",
                    "unit_symbol_snapshot",
                ],
                batch_size=500,
            )
            batch.clear()
    if batch:
        StockMovement.objects.bulk_update(
            batch,
            [
                "project_code_snapshot",
                "project_name_snapshot",
                "material_name_snapshot",
                "supplier_name_snapshot",
                "supplier_phone_snapshot",
                "supplier_phone_normalized_snapshot",
                "unit_symbol_snapshot",
            ],
            batch_size=500,
        )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_stockmovement")]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="project_code_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=30),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="project_name_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=180),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="material_name_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=180),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="supplier_name_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=180),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="supplier_phone_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=40),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="supplier_phone_normalized_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=40),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="unit_symbol_snapshot",
            field=models.CharField(blank=True, default="", editable=False, max_length=20),
        ),
        migrations.RunPython(populate_movement_snapshots, migrations.RunPython.noop),
    ]
