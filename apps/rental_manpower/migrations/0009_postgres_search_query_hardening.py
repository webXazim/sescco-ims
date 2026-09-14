from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import AddIndexConcurrently, TrigramExtension
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("rental_manpower", "0008_supplier_worker_termination"),
    ]

    operations = [
        TrigramExtension(),
        AddIndexConcurrently(
            model_name="rentalworker",
            index=GinIndex(fields=("worker_number",), name="rntl_wrk_num_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="rentalworker",
            index=GinIndex(fields=("full_name",), name="rntl_wrk_name_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="rentalworker",
            index=GinIndex(fields=("national_id",), name="rntl_wrk_nid_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="rentalworker",
            index=GinIndex(fields=("phone",), name="rntl_wrk_phone_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="workerassignment",
            index=models.Index(
                fields=("company", "project", "worker", "effective_from"),
                condition=Q(cancelled_at__isnull=True),
                name="rntl_asg_live_project_idx",
            ),
        ),
        AddIndexConcurrently(
            model_name="workerassignment",
            index=GinIndex(fields=("trade",), name="rntl_asg_trade_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="workerassignment",
            index=GinIndex(fields=("reason",), name="rntl_asg_reason_trgm", opclasses=("gin_trgm_ops",)),
        ),
        AddIndexConcurrently(
            model_name="workerassignment",
            index=GinIndex(fields=("end_reason",), name="rntl_asg_end_reason_trgm", opclasses=("gin_trgm_ops",)),
        ),
    ]
