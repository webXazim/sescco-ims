from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rental_manpower", "0005_alter_manpowersupplier_company_and_more")]

    operations = [
        migrations.AddField(model_name="manpowersupplier", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="manpowersupplier", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="rentalworker", name="inactive_on", field=models.DateField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="rentalworker", name="inactive_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddField(model_name="rentalworker", name="archived_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="rentalworker", name="archived_reason", field=models.CharField(blank=True, max_length=300)),
        migrations.AddIndex(model_name="manpowersupplier", index=models.Index(fields=["company", "archived_at", "name"], name="rntl_sup_archive_name_idx")),
        migrations.AddIndex(model_name="rentalworker", index=models.Index(fields=["company", "archived_at", "full_name"], name="rntl_wrk_archive_name_idx")),
    ]
