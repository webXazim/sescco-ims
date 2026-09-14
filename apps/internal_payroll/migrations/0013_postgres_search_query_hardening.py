from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import AddIndexConcurrently, TrigramExtension
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("internal_payroll", "0012_reversible_archive_lifecycle"),
    ]

    operations = [
        TrigramExtension(),
        AddIndexConcurrently(
            model_name="internalemployee",
            index=GinIndex(fields=("employee_number",), name="int_emp_num_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="internalemployee",
            index=GinIndex(fields=("full_name",), name="int_emp_name_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="internalemployee",
            index=GinIndex(fields=("national_id",), name="int_emp_nid_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="internalemployee",
            index=GinIndex(fields=("phone",), name="int_emp_phone_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="employeeorganizationassignment",
            index=models.Index(
                fields=("company", "branch", "employee"),
                condition=Q(effective_to__isnull=True),
                name="int_org_open_branch_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="employeeorganizationassignment",
            index=models.Index(
                fields=("company", "department", "employee"),
                condition=Q(effective_to__isnull=True),
                name="int_org_open_dept_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="employeeorganizationassignment",
            index=GinIndex(fields=("position",), name="int_org_pos_trgm", opclasses=("gin_trgm_ops",)),
        ),
    ]
