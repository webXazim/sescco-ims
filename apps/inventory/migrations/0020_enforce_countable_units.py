"""Require integer entries for recognisable discrete units (no balance rewrite)."""
from django.db import migrations

COUNTABLE = {
    "pc", "pcs", "pce", "piece", "pieces", "no", "nos", "nr", "number", "numbers",
    "each", "ea", "unit", "units", "set", "sets", "box", "boxes", "carton", "cartons",
    "bag", "bags", "pair", "pairs", "roll", "rolls", "pack", "packs", "packet", "packets",
    "kit", "kits", "laptop", "laptops", "bottle", "bottles", "can", "cans",
    "drum", "drums", "pallet", "pallets", "bundle", "bundles", "sheet", "sheets",
    "panel", "panels", "device", "devices", "machine", "machines", "item", "items",
}


def enforce_countable(apps, schema_editor):
    Unit = apps.get_model("inventory", "Unit")
    db = schema_editor.connection.alias
    for unit in Unit.objects.using(db).filter(allows_fractional_quantities=True).iterator():
        names = {str(unit.name or "").strip().casefold().rstrip("."),
                 str(unit.symbol or "").strip().casefold().rstrip(".")}
        if names & COUNTABLE:
            Unit.objects.using(db).filter(pk=unit.pk).update(allows_fractional_quantities=False)
    # Deliberately do not modify StockItem quantities, prices or StockMovement history.


class Migration(migrations.Migration):
    dependencies = [("inventory", "0019_approval_requests_and_unit_defaults")]
    operations = [migrations.RunPython(enforce_countable, migrations.RunPython.noop)]
