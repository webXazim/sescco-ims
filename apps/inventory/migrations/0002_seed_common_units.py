from django.db import migrations


COMMON_UNITS = (
    ("Bag", "bag"),
    ("Piece", "pc"),
    ("Box", "box"),
    ("Kilogram", "kg"),
    ("Meter", "m"),
    ("Liter", "L"),
    ("Pair", "pair"),
    ("Roll", "roll"),
)


def seed_units(apps, schema_editor):
    Unit = apps.get_model("inventory", "Unit")
    for name, symbol in COMMON_UNITS:
        Unit.objects.get_or_create(
            normalized_name=name.casefold(),
            defaults={
                "name": name,
                "symbol": symbol,
                "normalized_symbol": symbol.casefold(),
                "is_active": True,
            },
        )


def remove_seeded_units(apps, schema_editor):
    Unit = apps.get_model("inventory", "Unit")
    Unit.objects.filter(normalized_name__in=[name.casefold() for name, _ in COMMON_UNITS]).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(seed_units, migrations.RunPython.noop)]
