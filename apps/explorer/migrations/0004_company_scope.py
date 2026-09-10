import django.db.models.deletion
from django.db import migrations, models


def backfill_explorer_company(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    CompanyMembership = apps.get_model("accounts", "CompanyMembership")
    SavedView = apps.get_model("explorer", "SavedView")
    TablePreference = apps.get_model("explorer", "TablePreference")
    companies = list(Company.objects.values_list("pk", flat=True)[:2])
    fallback = companies[0] if len(companies) == 1 else None

    def owner_company(owner_id):
        memberships = list(
            CompanyMembership.objects.filter(user_id=owner_id, is_active=True)
            .values_list("company_id", flat=True)[:2]
        )
        if len(memberships) == 1:
            return memberships[0]
        if fallback is not None:
            return fallback
        raise RuntimeError(
            f"Cannot safely determine legacy explorer ownership for user {owner_id}."
        )

    for row in SavedView.objects.filter(company__isnull=True).iterator():
        SavedView.objects.filter(pk=row.pk).update(company_id=owner_company(row.owner_id))
    for row in TablePreference.objects.filter(company__isnull=True).iterator():
        TablePreference.objects.filter(pk=row.pk).update(company_id=owner_company(row.owner_id))


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_backfill_initial_company_access"),
        ("core", "0001_platform_core"),
        ("explorer", "0003_add_stock_value_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="savedview",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="saved_inventory_views", to="core.company"),
        ),
        migrations.AddField(
            model_name="tablepreference",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="inventory_table_preferences", to="core.company"),
        ),
        migrations.RunPython(backfill_explorer_company, migrations.RunPython.noop),
        migrations.AlterField(model_name="savedview", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_inventory_views", to="core.company")),
        migrations.AlterField(model_name="tablepreference", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_table_preferences", to="core.company")),
        migrations.RemoveConstraint(model_name="savedview", name="uniq_saved_view_name_per_owner_type"),
        migrations.RemoveConstraint(model_name="tablepreference", name="uniq_table_preference_owner_view"),
        migrations.AddConstraint(model_name="savedview", constraint=models.UniqueConstraint(fields=("company", "owner", "view_type", "name"), name="saved_view_company_owner_name_uniq")),
        migrations.AddConstraint(model_name="tablepreference", constraint=models.UniqueConstraint(fields=("company", "owner", "view_type"), name="table_pref_company_owner_view_uniq")),
        migrations.AddIndex(model_name="savedview", index=models.Index(fields=["company", "owner", "view_type"], name="saved_view_company_idx")),
        migrations.AddIndex(model_name="tablepreference", index=models.Index(fields=["company", "owner", "view_type"], name="table_pref_company_idx")),
    ]
