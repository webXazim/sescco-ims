import django.db.models.deletion
from django.db import migrations, models


def backfill_locations(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    InventoryLocation = apps.get_model("inventory", "InventoryLocation")
    StockItem = apps.get_model("inventory", "StockItem")
    StockMovement = apps.get_model("inventory", "StockMovement")

    for project in Project.objects.all().iterator():
        location, _ = InventoryLocation.objects.update_or_create(
            project_id=project.pk,
            defaults={
                "code": project.code,
                "name": project.name,
                "location_type": "project",
                "is_active": project.deleted_at is None,
            },
        )
        StockItem.objects.filter(project_id=project.pk, location__isnull=True).update(
            location_id=location.pk,
            condition="new",
        )

    office_code = "OFFICE"
    suffix = 1
    while InventoryLocation.objects.filter(code=office_code).exists():
        suffix += 1
        office_code = f"OFFICE-{suffix}"
    InventoryLocation.objects.get_or_create(
        location_type="office",
        project__isnull=True,
        defaults={"code": office_code, "name": "Main Office", "is_active": True},
    )

    for movement in StockMovement.objects.select_related("stock_item__location").iterator():
        item = movement.stock_item
        location = item.location
        updates = {}
        if not movement.location_code_snapshot:
            updates["location_code_snapshot"] = location.code
        if not movement.location_name_snapshot:
            updates["location_name_snapshot"] = location.name
        if not movement.condition_snapshot:
            updates["condition_snapshot"] = item.condition
        if updates:
            StockMovement.objects.filter(pk=movement.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0009_inventorylocation_stocktransfer_stocktransferline_and_more")]

    operations = [
        migrations.RunPython(backfill_locations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stockitem",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_items",
                to="inventory.inventorylocation",
            ),
        ),
    ]
