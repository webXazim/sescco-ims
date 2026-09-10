import django.db.models.deletion
from django.db import migrations, models

import apps.projects.models


def backfill_project_company(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    Project = apps.get_model("projects", "Project")
    companies = list(Company.objects.values_list("pk", flat=True)[:2])
    if len(companies) != 1:
        raise RuntimeError(
            "Inventory tenant migration requires exactly one existing company before legacy "
            "Project rows can be assigned safely."
        )
    Project.objects.filter(company__isnull=True).update(company_id=companies[0])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_backfill_initial_company_access"),
        ("core", "0001_platform_core"),
        ("projects", "0002_project_deleted_at_project_deleted_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects",
                to="core.company",
            ),
        ),
        migrations.RunPython(backfill_project_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="project",
            name="code",
            field=models.CharField(
                help_text="Short project tag shown across inventory, for example ARAMCO-01.",
                max_length=30,
                validators=[apps.projects.models.project_code_validator],
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(
                fields=("company", "code"), name="projects_company_code_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(
                fields=["company", "status", "code"], name="project_company_status_idx"
            ),
        ),
    ]
