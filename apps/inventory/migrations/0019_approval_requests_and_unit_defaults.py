from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid

COUNTABLE_NAMES = {"piece", "pieces", "pcs", "pc", "nos", "no", "number", "numbers", "unit", "units", "each", "ea", "set", "sets", "box", "boxes", "bag", "bags", "pair", "pairs", "roll", "rolls", "pack", "packs", "kit", "kits", "laptop", "laptops"}
MEASURABLE_NAMES = {"kilogram", "kilograms", "kg", "gram", "grams", "g", "meter", "metre", "meters", "metres", "m", "square meter", "square metre", "sqm", "m2", "m²", "cubic meter", "cubic metre", "cbm", "m3", "m³", "liter", "litre", "liters", "litres", "l", "ton", "tons", "tonne", "tonnes", "ft", "feet", "yard", "yards"}


def classify_units(apps, schema_editor):
    Unit = apps.get_model("inventory", "Unit")
    StockItem = apps.get_model("inventory", "StockItem")
    db = schema_editor.connection.alias
    for unit in Unit.objects.using(db).all().iterator():
        tokens = {unit.name.strip().casefold(), unit.symbol.strip().casefold()}
        if tokens & MEASURABLE_NAMES:
            # A deliberately configured measurable unit remains fractional.
            continue
        if not tokens & COUNTABLE_NAMES:
            # Unknown/custom units are left unchanged; administrator can classify them.
            continue
        if any(
            value is not None and value % 1
            for stock in StockItem.objects.using(db).filter(unit_id=unit.pk).values("current_quantity", "minimum_quantity").iterator()
            for value in (stock["current_quantity"], stock["minimum_quantity"])
        ):
            continue
        Unit.objects.using(db).filter(pk=unit.pk).update(allows_fractional_quantities=False)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0018_unit_allows_fractional_quantities"),
        ("projects", "0007_inventory_manager"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AlterField(model_name="unit", name="allows_fractional_quantities", field=models.BooleanField(
            default=False, help_text="Use whole numbers by default for pieces, laptops, boxes and sets; enable decimals for measured units.",
        )),
        migrations.CreateModel(
            name="StockApprovalRequest",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("reference", models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
                ("idempotency_key", models.UUIDField(editable=False)),
                ("kind", models.CharField(max_length=12, choices=[("receipt", "Stock receipt"), ("transfer", "Stock transfer")])),
                ("status", models.CharField(max_length=12, default="pending", choices=[("pending", "Pending"), ("approved", "Approved / applied"), ("rejected", "Rejected")])),
                ("payload", models.JSONField(default=dict)),
                ("attachment", models.FileField(blank=True, upload_to="stock-approvals/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("company", models.ForeignKey(to="core.company", on_delete=django.db.models.deletion.PROTECT, related_name="stock_approval_requests")),
                ("requested_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="requested_stock_approvals")),
                ("applied_movement", models.OneToOneField(to="inventory.stockmovement", on_delete=django.db.models.deletion.PROTECT, blank=True, null=True, related_name="approval_request")),
                ("applied_transfer", models.OneToOneField(to="inventory.stocktransfer", on_delete=django.db.models.deletion.PROTECT, blank=True, null=True, related_name="approval_request")),
            ],
            options={
                "ordering": ("-created_at", "-pk"),
                "constraints": [models.UniqueConstraint(fields=("company", "kind", "idempotency_key"), name="stock_approval_company_idem_uniq")],
                "indexes": [models.Index(fields=("company", "status", "-created_at"), name="stock_approval_queue_idx")],
            },
        ),
        migrations.CreateModel(
            name="StockApprovalDecision",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("status", models.CharField(max_length=12, default="pending", choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")])),
                ("reason", models.CharField(max_length=500, blank=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decided_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_approval_decisions")),
                ("project", models.ForeignKey(to="projects.project", on_delete=django.db.models.deletion.PROTECT, related_name="stock_approval_decisions")),
                ("request", models.ForeignKey(to="inventory.stockapprovalrequest", on_delete=django.db.models.deletion.PROTECT, related_name="decisions")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("request", "project"), name="stock_approval_project_uniq")]},
        ),
        migrations.RunPython(classify_units, migrations.RunPython.noop),
    ]
