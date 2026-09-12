from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("internal_payroll", "0010_secondary_configuration_lifecycle"),
    ]

    operations = [
        *[
            migrations.AddField(
                model_name=model,
                name="deleted_at",
                field=models.DateTimeField(blank=True, db_index=True, null=True),
            )
            for model in ("branch", "department", "internalemployee")
        ],
        *[
            migrations.AddField(
                model_name=model,
                name="purge_after",
                field=models.DateTimeField(blank=True, db_index=True, null=True),
            )
            for model in ("branch", "department", "internalemployee")
        ],
        *[
            migrations.AddField(
                model_name=model,
                name="deletion_reason",
                field=models.CharField(blank=True, max_length=500),
            )
            for model in ("branch", "department", "internalemployee")
        ],
        migrations.AddField(
            model_name="branch",
            name="deleted_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="internal_branches_deleted", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="department",
            name="deleted_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="internal_departments_deleted", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="internalemployee",
            name="deleted_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="internal_employees_deleted", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(model_name="branch", index=models.Index(fields=["company", "deleted_at", "name"], name="int_branch_trash_idx")),
        migrations.AddIndex(model_name="department", index=models.Index(fields=["company", "deleted_at", "name"], name="int_dept_trash_idx")),
        migrations.AddIndex(model_name="internalemployee", index=models.Index(fields=["company", "deleted_at", "full_name"], name="int_emp_trash_idx")),
    ]
