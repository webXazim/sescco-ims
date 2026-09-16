from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0006_scale_finder_indexes"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="sourcingmanpowercontact",
            old_name="src_mpcontact_supplier_active_idx",
            new_name="src_mpc_supplier_active_idx",
        ),
    ]
