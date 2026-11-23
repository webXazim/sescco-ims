from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("data_exchange", "0002_company_scope"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exportaudit",
            name="dataset",
            field=models.CharField(
                choices=[
                    ("inventory", "Inventory"),
                    ("low_stock", "Low stock"),
                    ("activity", "Stock activity"),
                    ("stock_history", "Stock history"),
                    ("project_inventory", "Project inventory"),
                    ("opening_template", "Opening-stock template"),
                    ("transfer_worksheet", "Stock transfer worksheet"),
                ],
                max_length=32,
            ),
        ),
    ]
