from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("internal_payroll", "0011_master_trash_retention"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="internalemployee",
            name="internal_employee_archive_requires_stopped_status",
        ),
    ]
