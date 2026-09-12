from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("internal_payroll", "0006_alter_attendanceentry_company_and_more")]

    operations = [
        migrations.AddField(
            model_name="internalemployee",
            name="address",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="salarypaymentrow",
            name="employee_address",
            field=models.CharField(blank=True, max_length=300),
        ),
    ]
