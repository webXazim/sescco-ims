from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_inventory_archive_metadata(apps, schema_editor):
    Unit = apps.get_model("inventory", "Unit")
    Supplier = apps.get_model("inventory", "Supplier")
    StockItem = apps.get_model("inventory", "StockItem")
    InventoryLocation = apps.get_model("inventory", "InventoryLocation")

    for model in (Unit, Supplier):
        for row in model.objects.filter(is_active=False, archived_at__isnull=True).iterator():
            model.objects.filter(pk=row.pk).update(
                archived_at=row.updated_at,
                archived_reason="Migrated from the existing archived state.",
            )
    for row in StockItem.objects.filter(status="archived", archived_at__isnull=True).iterator():
        StockItem.objects.filter(pk=row.pk).update(
            archived_at=row.updated_at,
            archived_reason="Migrated from the existing archived stock state.",
        )
    for row in InventoryLocation.objects.filter(location_type="office", is_active=False, archived_at__isnull=True).iterator():
        InventoryLocation.objects.filter(pk=row.pk).update(
            archived_at=row.updated_at,
            archived_reason="Migrated from the existing inactive office-location state.",
        )
    # Project locations are lifecycle mirrors of the shared Project master.
    # Existing installations may have project locations left active by the legacy
    # signal even when the project is on hold, completed, archived, or in Trash.
    for location in InventoryLocation.objects.filter(location_type="project").select_related("project").iterator():
        project = location.project
        is_archived = project.status == "archived"
        InventoryLocation.objects.filter(pk=location.pk).update(
            is_active=(project.status == "active" and project.deleted_at is None),
            archived_at=(project.archived_at if is_archived else None),
            archived_reason=(project.archived_reason if is_archived else ""),
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0013_company_scope"),
        ("projects", "0005_project_archive_metadata"),
    ]

    operations = [
        migrations.AddField(model_name="unit", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="unit", name="archived_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="supplier", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="supplier", name="archived_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="stockitem", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="stockitem", name="archived_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="inventorylocation", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="inventorylocation", name="archived_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="inventorylocation", name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="inventorylocation", name="purge_after", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="inventorylocation", name="deletion_reason", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="inventorylocation",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inventory_locations_deleted",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_inventory_archive_metadata, migrations.RunPython.noop),
    ]
