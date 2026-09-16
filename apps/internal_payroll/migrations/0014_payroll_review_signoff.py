from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_internal_finance_permission_decomposition"),
        ("internal_payroll", "0013_postgres_search_query_hardening"),
    ]

    operations = [
        migrations.AddField(
            model_name="payrollrun",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payrollrun",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_internal_payroll_runs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
