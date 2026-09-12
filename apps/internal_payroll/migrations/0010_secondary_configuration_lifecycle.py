from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("internal_payroll", "0009_organization_master_lifecycle")]

    operations = [
        migrations.AddField(model_name="salarycomponent", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="salarycomponent", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="overtimepolicy", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="overtimepolicy", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="bankexporttemplate", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="bankexporttemplate", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddIndex(model_name="salarycomponent", index=models.Index(fields=["company", "archived_at", "category"], name="int_sal_comp_archive_idx")),
        migrations.AddIndex(model_name="overtimepolicy", index=models.Index(fields=["company", "archived_at", "name"], name="int_ot_policy_archive_idx")),
        migrations.AddIndex(model_name="bankexporttemplate", index=models.Index(fields=["company", "channel", "archived_at"], name="int_bank_template_archive_idx")),
    ]
