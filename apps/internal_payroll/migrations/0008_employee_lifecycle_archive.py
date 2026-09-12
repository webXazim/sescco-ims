from django.db import migrations, models
from django.db.models import Q


def close_existing_terminated_assignments(apps, schema_editor):
    Employee = apps.get_model("internal_payroll", "InternalEmployee")
    Assignment = apps.get_model("internal_payroll", "EmployeeOrganizationAssignment")
    for employee in Employee.objects.filter(status="terminated", employment_end_date__isnull=False).iterator():
        Assignment.objects.filter(
            employee_id=employee.pk, effective_to__isnull=True, effective_from__lte=employee.employment_end_date
        ).update(effective_to=employee.employment_end_date)


class Migration(migrations.Migration):
    dependencies = [("internal_payroll", "0007_employee_address_payment_snapshot")]

    operations = [
        migrations.AddField(
            model_name="internalemployee",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="internalemployee",
            name="archived_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.RunPython(close_existing_terminated_assignments, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="internalemployee",
            constraint=models.CheckConstraint(
                condition=Q(archived_at__isnull=True) | Q(status__in=["inactive", "terminated"]),
                name="internal_employee_archive_requires_stopped_status",
            ),
        ),
    ]
