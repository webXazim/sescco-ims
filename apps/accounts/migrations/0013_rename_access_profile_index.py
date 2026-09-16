from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_sourcing_access_control_authority"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="accessprofile",
            old_name="acct_profile_company_active_idx",
            new_name="acct_prof_company_active_idx",
        ),
    ]
