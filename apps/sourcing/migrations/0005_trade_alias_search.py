from django.db import migrations, models


def populate_normalized_aliases(apps, schema_editor):
    Trade = apps.get_model("sourcing", "SourcingTrade")
    for trade in Trade.objects.all().iterator(chunk_size=500):
        aliases = []
        seen = {" ".join(str(trade.name or "").strip().split()).casefold()}
        normalized = []
        for raw in trade.aliases or []:
            alias = " ".join(str(raw or "").strip().split())
            key = alias.casefold()
            if alias and key not in seen:
                aliases.append(alias)
                normalized.append(key)
                seen.add(key)
        Trade.objects.filter(pk=trade.pk).update(
            aliases=aliases,
            normalized_aliases="\n".join(normalized),
        )


class Migration(migrations.Migration):
    dependencies = [("sourcing", "0004_manpower_supplier_contacts")]

    operations = [
        migrations.AddField(
            model_name="sourcingtrade",
            name="normalized_aliases",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.RunPython(populate_normalized_aliases, migrations.RunPython.noop),
    ]
