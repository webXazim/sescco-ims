from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_trash_cascade_link"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="area",
            field=models.CharField(
                choices=[
                    ("access", "Access"),
                    ("core", "Platform Core"),
                    ("projects", "Projects"),
                    ("inventory", "Inventory"),
                    ("data_exchange", "Data Exchange"),
                    ("internal", "Internal Payroll"),
                    ("rental", "Rental Manpower"),
                    ("documents", "Documents"),
                    ("management", "Management"),
                    ("sourcing", "Sourcing"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
