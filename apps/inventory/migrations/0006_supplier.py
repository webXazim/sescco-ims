from django.db import migrations, models


def copy_existing_suppliers(apps, schema_editor):
    StockItem = apps.get_model("inventory", "StockItem")
    Supplier = apps.get_model("inventory", "Supplier")
    seen = set()
    rows = StockItem.objects.order_by("pk").values(
        "supplier_name",
        "normalized_supplier_name",
        "supplier_phone",
        "normalized_supplier_phone",
        "supplier_location",
    )
    suppliers = []
    for row in rows.iterator():
        identity = (
            row["normalized_supplier_name"],
            row["normalized_supplier_phone"],
        )
        if not all(identity) or identity in seen:
            continue
        seen.add(identity)
        suppliers.append(
            Supplier(
                name=row["supplier_name"],
                normalized_name=identity[0],
                phone=row["supplier_phone"],
                normalized_phone=identity[1],
                location=row["supplier_location"],
            )
        )
    Supplier.objects.bulk_create(suppliers, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_explorer_indexes")]

    operations = [
        migrations.CreateModel(
            name="Supplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("normalized_name", models.CharField(editable=False, max_length=180)),
                ("phone", models.CharField(max_length=40)),
                ("normalized_phone", models.CharField(editable=False, max_length=40)),
                ("location", models.CharField(blank=True, max_length=180)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("name", "phone")},
        ),
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(
                fields=("normalized_name", "normalized_phone"),
                name="uniq_supplier_identity",
            ),
        ),
        migrations.AddIndex(
            model_name="supplier",
            index=models.Index(fields=["normalized_name"], name="supplier_name_norm_idx"),
        ),
        migrations.AddIndex(
            model_name="supplier",
            index=models.Index(fields=["normalized_phone"], name="supplier_phone_norm_idx"),
        ),
        migrations.RunPython(copy_existing_suppliers, migrations.RunPython.noop),
    ]
