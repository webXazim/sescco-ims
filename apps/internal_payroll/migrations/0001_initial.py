import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_platform_core"),
    ]

    operations = [
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=160)),
                ("location", models.CharField(blank=True, max_length=160)),
                ("address", models.TextField(blank=True)),
                ("manager_name", models.CharField(blank=True, max_length=160)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="internal_payroll_branch_records",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "internal_branch", "ordering": ("code", "name")},
        ),
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=160)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="internal_payroll_department_records",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "internal_department", "ordering": ("code", "name")},
        ),
        migrations.CreateModel(
            name="InternalEmployee",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("employee_number", models.CharField(max_length=40)),
                ("full_name", models.CharField(max_length=200)),
                ("national_id", models.CharField(blank=True, max_length=50)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("joining_date", models.DateField()),
                ("employment_end_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("on_leave", "On Leave"), ("inactive", "Inactive"), ("terminated", "Terminated")], db_index=True, default="active", max_length=20)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="internal_payroll_internalemployee_records",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "internal_employee", "ordering": ("employee_number", "full_name")},
        ),
        migrations.CreateModel(
            name="EmployeeOrganizationAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("position", models.CharField(max_length=160)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, max_length=300)),
                (
                    "branch",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employee_assignments", to="internal_payroll.branch"),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="internal_payroll_employeeorganizationassignment_records",
                        to="core.company",
                    ),
                ),
                (
                    "department",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="employee_assignments", to="internal_payroll.department"),
                ),
                (
                    "employee",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="organization_assignments", to="internal_payroll.internalemployee"),
                ),
            ],
            options={"db_table": "internal_employee_org_assignment", "ordering": ("-effective_from", "-created_at")},
        ),
        migrations.AddConstraint(model_name="branch", constraint=models.UniqueConstraint(fields=("company", "code"), name="internal_branch_company_code_uniq")),
        migrations.AddConstraint(model_name="branch", constraint=models.UniqueConstraint(fields=("company", "name"), name="internal_branch_company_name_uniq")),
        migrations.AddIndex(model_name="branch", index=models.Index(fields=["company", "is_active", "name"], name="int_branch_company_active_idx")),
        migrations.AddConstraint(model_name="department", constraint=models.UniqueConstraint(fields=("company", "code"), name="internal_department_company_code_uniq")),
        migrations.AddConstraint(model_name="department", constraint=models.UniqueConstraint(fields=("company", "name"), name="internal_department_company_name_uniq")),
        migrations.AddIndex(model_name="department", index=models.Index(fields=["company", "is_active", "name"], name="int_dept_company_active_idx")),
        migrations.AddConstraint(model_name="internalemployee", constraint=models.UniqueConstraint(fields=("company", "employee_number"), name="internal_employee_company_number_uniq")),
        migrations.AddConstraint(model_name="internalemployee", constraint=models.UniqueConstraint(condition=~Q(national_id=""), fields=("company", "national_id"), name="internal_employee_company_national_id_uniq")),
        migrations.AddConstraint(model_name="internalemployee", constraint=models.CheckConstraint(condition=Q(status__in=["active", "on_leave", "inactive", "terminated"]), name="internal_employee_status_valid")),
        migrations.AddConstraint(model_name="internalemployee", constraint=models.CheckConstraint(condition=Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=models.F("joining_date")), name="internal_employee_end_after_join")),
        migrations.AddConstraint(model_name="internalemployee", constraint=models.CheckConstraint(condition=~Q(status="terminated") | Q(employment_end_date__isnull=False), name="internal_employee_terminated_has_end")),
        migrations.AddIndex(model_name="internalemployee", index=models.Index(fields=["company", "status", "full_name"], name="int_emp_company_status_idx")),
        migrations.AddIndex(model_name="internalemployee", index=models.Index(fields=["company", "joining_date"], name="int_emp_company_join_idx")),
        migrations.AddConstraint(model_name="employeeorganizationassignment", constraint=models.CheckConstraint(condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")), name="internal_emp_org_valid_date_range")),
        migrations.AddConstraint(model_name="employeeorganizationassignment", constraint=models.UniqueConstraint(condition=Q(effective_to__isnull=True), fields=("employee",), name="internal_emp_org_one_open_assignment")),
        migrations.AddIndex(model_name="employeeorganizationassignment", index=models.Index(fields=["company", "employee", "-effective_from"], name="int_org_company_emp_date_idx")),
        migrations.AddIndex(model_name="employeeorganizationassignment", index=models.Index(fields=["company", "branch", "effective_from"], name="int_org_company_branch_idx")),
        migrations.AddIndex(model_name="employeeorganizationassignment", index=models.Index(fields=["company", "department", "effective_from"], name="int_org_company_dept_idx")),
    ]
