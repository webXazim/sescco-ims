from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("internal_payroll", "0008_employee_lifecycle_archive")]

    operations = [
        migrations.AddField(model_name="branch", name="kind", field=models.CharField(choices=[("branch", "Branch"), ("office", "Office")], db_index=True, default="branch", max_length=20)),
        migrations.AddField(model_name="branch", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="branch", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="department", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="department", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddIndex(model_name="branch", index=models.Index(fields=["company", "archived_at", "name"], name="int_branch_company_archive_idx")),
        migrations.AddIndex(model_name="department", index=models.Index(fields=["company", "archived_at", "name"], name="int_dept_company_archive_idx")),
    ]
