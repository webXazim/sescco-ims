from django.db import migrations


def create_missing_company_offices(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    InventoryLocation = apps.get_model("inventory", "InventoryLocation")
    for company in Company.objects.all().iterator():
        # Respect existing active, archived and deleted office identities.
        if InventoryLocation.objects.filter(company_id=company.pk, location_type="office").exists():
            continue
        code = "OFFICE"
        suffix = 1
        while InventoryLocation.objects.filter(company_id=company.pk, code=code).exists():
            suffix += 1
            code = f"OFFICE-{suffix}"
        InventoryLocation.objects.create(
            company_id=company.pk,
            code=code,
            name="Main Office",
            location_type="office",
            is_active=True,
        )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0014_inventory_master_lifecycle")]
    operations = [migrations.RunPython(create_missing_company_offices, migrations.RunPython.noop)]
