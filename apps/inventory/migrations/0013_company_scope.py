import django.db.models.deletion
from django.db import migrations, models


def _single_company_id(Company):
    companies = list(Company.objects.values_list("pk", flat=True)[:2])
    if len(companies) != 1:
        raise RuntimeError(
            "Inventory tenant migration requires exactly one existing company before legacy "
            "Inventory rows can be assigned safely."
        )
    return companies[0]


def backfill_inventory_company(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    Unit = apps.get_model("inventory", "Unit")
    Supplier = apps.get_model("inventory", "Supplier")
    InventoryLocation = apps.get_model("inventory", "InventoryLocation")
    StockItem = apps.get_model("inventory", "StockItem")
    StockDocument = apps.get_model("inventory", "StockDocument")
    StockMovement = apps.get_model("inventory", "StockMovement")
    StockTransfer = apps.get_model("inventory", "StockTransfer")
    company_id = _single_company_id(Company)

    Unit.objects.filter(company__isnull=True).update(company_id=company_id)
    Supplier.objects.filter(company__isnull=True).update(company_id=company_id)

    for location in InventoryLocation.objects.select_related("project").iterator():
        derived = location.project.company_id if location.project_id else company_id
        if location.company_id and location.company_id != derived:
            raise RuntimeError(f"InventoryLocation {location.pk} has conflicting company ownership.")
        if not location.company_id:
            InventoryLocation.objects.filter(pk=location.pk).update(company_id=derived)

    for item in StockItem.objects.select_related("project", "location", "unit").iterator():
        derived = item.location.company_id
        if item.project_id and item.project.company_id != derived:
            raise RuntimeError(f"StockItem {item.pk} project/location cross company boundary.")
        if item.unit.company_id != derived:
            raise RuntimeError(f"StockItem {item.pk} unit/location cross company boundary.")
        if item.company_id and item.company_id != derived:
            raise RuntimeError(f"StockItem {item.pk} has conflicting company ownership.")
        if not item.company_id:
            StockItem.objects.filter(pk=item.pk).update(company_id=derived)

    for document in StockDocument.objects.select_related("stock_item").iterator():
        derived = document.stock_item.company_id
        if document.company_id and document.company_id != derived:
            raise RuntimeError(f"StockDocument {document.pk} has conflicting company ownership.")
        if not document.company_id:
            StockDocument.objects.filter(pk=document.pk).update(company_id=derived)

    for movement in StockMovement.objects.select_related("stock_item", "reversal_of").iterator():
        derived = movement.stock_item.company_id
        if movement.reversal_of_id and movement.reversal_of.company_id not in (None, derived):
            raise RuntimeError(f"StockMovement {movement.pk} reversal crosses company boundary.")
        if movement.company_id and movement.company_id != derived:
            raise RuntimeError(f"StockMovement {movement.pk} has conflicting company ownership.")
        if not movement.company_id:
            StockMovement.objects.filter(pk=movement.pk).update(company_id=derived)

    for transfer in StockTransfer.objects.select_related(
        "source_location", "destination_location"
    ).iterator():
        source_company = transfer.source_location.company_id
        if transfer.destination_location.company_id != source_company:
            raise RuntimeError(f"StockTransfer {transfer.pk} crosses company boundary.")
        if transfer.company_id and transfer.company_id != source_company:
            raise RuntimeError(f"StockTransfer {transfer.pk} has conflicting company ownership.")
        if not transfer.company_id:
            StockTransfer.objects.filter(pk=transfer.pk).update(company_id=source_company)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_platform_core"),
        ("projects", "0003_company_scope"),
        ("inventory", "0012_alter_inventorylocation_project"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_units", to="core.company"),
        ),
        migrations.AddField(
            model_name="supplier",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="material_suppliers", to="core.company"),
        ),
        migrations.AddField(
            model_name="inventorylocation",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_locations", to="core.company"),
        ),
        migrations.AddField(
            model_name="stockitem",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_items", to="core.company"),
        ),
        migrations.AddField(
            model_name="stockdocument",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_documents", to="core.company"),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="core.company"),
        ),
        migrations.AddField(
            model_name="stocktransfer",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_transfers", to="core.company"),
        ),
        migrations.RunPython(backfill_inventory_company, migrations.RunPython.noop),
        migrations.AlterField(model_name="unit", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_units", to="core.company")),
        migrations.AlterField(model_name="supplier", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="material_suppliers", to="core.company")),
        migrations.AlterField(model_name="inventorylocation", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_locations", to="core.company")),
        migrations.AlterField(model_name="stockitem", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_items", to="core.company")),
        migrations.AlterField(model_name="stockdocument", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_documents", to="core.company")),
        migrations.AlterField(model_name="stockmovement", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="core.company")),
        migrations.AlterField(model_name="stocktransfer", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_transfers", to="core.company")),
        migrations.AlterField(model_name="stockmovement", name="idempotency_key", field=models.UUIDField(editable=False)),
        migrations.AlterField(model_name="stocktransfer", name="idempotency_key", field=models.UUIDField(editable=False)),
        migrations.AlterField(model_name="stocktransfer", name="reversal_idempotency_key", field=models.UUIDField(blank=True, editable=False, null=True)),
        migrations.AlterField(model_name="unit", name="normalized_name", field=models.CharField(editable=False, max_length=80)),
        migrations.AlterField(model_name="unit", name="normalized_symbol", field=models.CharField(editable=False, max_length=20)),
        migrations.AlterField(model_name="inventorylocation", name="code", field=models.CharField(max_length=30)),
        migrations.RemoveConstraint(model_name="supplier", name="uniq_supplier_identity"),
        migrations.RemoveConstraint(model_name="stockitem", name="uniq_stock_identity_per_location_condition"),
        migrations.AddConstraint(model_name="stockmovement", constraint=models.UniqueConstraint(fields=("company", "idempotency_key"), name="movement_company_idempotency_uniq")),
        migrations.AddConstraint(model_name="stocktransfer", constraint=models.UniqueConstraint(fields=("company", "idempotency_key"), name="transfer_company_idempotency_uniq")),
        migrations.AddConstraint(model_name="stocktransfer", constraint=models.UniqueConstraint(fields=("company", "reversal_idempotency_key"), name="transfer_company_reversal_idem_uniq")),
        migrations.AddConstraint(model_name="unit", constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="unit_company_name_uniq")),
        migrations.AddConstraint(model_name="unit", constraint=models.UniqueConstraint(fields=("company", "normalized_symbol"), name="unit_company_symbol_uniq")),
        migrations.AddConstraint(model_name="supplier", constraint=models.UniqueConstraint(fields=("company", "normalized_name", "normalized_phone"), name="supplier_company_identity_uniq")),
        migrations.AddConstraint(model_name="inventorylocation", constraint=models.UniqueConstraint(fields=("company", "code"), name="location_company_code_uniq")),
        migrations.AddConstraint(model_name="stockitem", constraint=models.UniqueConstraint(fields=("company", "location", "normalized_material_name", "normalized_supplier_name", "normalized_supplier_phone", "condition"), name="stock_company_location_identity_uniq")),
        migrations.AddIndex(model_name="unit", index=models.Index(fields=["company", "is_active", "name"], name="unit_company_active_idx")),
        migrations.AddIndex(model_name="supplier", index=models.Index(fields=["company", "is_active", "normalized_name"], name="supplier_company_active_idx")),
        migrations.AddIndex(model_name="inventorylocation", index=models.Index(fields=["company", "is_active", "code"], name="location_company_active_idx")),
        migrations.AddIndex(model_name="stockitem", index=models.Index(fields=["company", "status", "updated_at"], name="stock_company_status_idx")),
        migrations.AddIndex(model_name="stockmovement", index=models.Index(fields=["company", "-movement_date", "-created_at"], name="move_company_date_idx")),
        migrations.AddIndex(model_name="stocktransfer", index=models.Index(fields=["company", "-transfer_date", "-created_at"], name="transfer_company_date_idx")),
    ]
