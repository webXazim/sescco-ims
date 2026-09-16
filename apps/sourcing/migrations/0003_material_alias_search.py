from __future__ import annotations

from django.db import migrations, models


def backfill_normalized_aliases(apps, schema_editor):
    Material = apps.get_model("sourcing", "SourcingMaterial")
    for material in Material.objects.all().iterator(chunk_size=500):
        normalized = []
        seen = set()
        for raw in material.aliases or []:
            value = " ".join(str(raw or "").strip().split()).casefold()
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)
        material.normalized_aliases = "\n".join(normalized)
        material.save(update_fields=["normalized_aliases"])


class Migration(migrations.Migration):
    dependencies = [("sourcing", "0002_vendor_directory_master")]

    operations = [
        migrations.AddField(
            model_name="sourcingmaterial",
            name="normalized_aliases",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.RunPython(backfill_normalized_aliases, migrations.RunPython.noop),
    ]
