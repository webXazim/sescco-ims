import django.db.models.deletion
from django.db import migrations, models


def backfill_exchange_company(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    ImportJob = apps.get_model("data_exchange", "ImportJob")
    ExportAudit = apps.get_model("data_exchange", "ExportAudit")
    companies = list(Company.objects.values_list("pk", flat=True)[:2])
    if len(companies) != 1:
        raise RuntimeError(
            "Inventory tenant migration requires exactly one existing company before legacy "
            "import/export records can be assigned safely."
        )
    fallback = companies[0]
    for job in ImportJob.objects.select_related("project").iterator():
        derived = job.project.company_id if job.project_id else fallback
        if not job.company_id:
            ImportJob.objects.filter(pk=job.pk).update(company_id=derived)
    ExportAudit.objects.filter(company__isnull=True).update(company_id=fallback)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_platform_core"),
        ("projects", "0003_company_scope"),
        ("inventory", "0013_company_scope"),
        ("data_exchange", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_import_jobs", to="core.company"),
        ),
        migrations.AddField(
            model_name="exportaudit",
            name="company",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="inventory_export_audits", to="core.company"),
        ),
        migrations.RunPython(backfill_exchange_company, migrations.RunPython.noop),
        migrations.AlterField(model_name="importjob", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_import_jobs", to="core.company")),
        migrations.AlterField(model_name="exportaudit", name="company", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="inventory_export_audits", to="core.company")),
        migrations.AddIndex(model_name="importjob", index=models.Index(fields=["company", "status", "-created_at"], name="import_company_status_idx")),
        migrations.AddIndex(model_name="exportaudit", index=models.Index(fields=["company", "dataset", "-created_at"], name="export_company_dataset_idx")),
    ]
