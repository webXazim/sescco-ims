"""Track requester cancellation of pending, unposted stock transfer requests."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0020_enforce_countable_units"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockapprovalrequest", name="status",
            field=models.CharField(
                max_length=12, default="pending",
                choices=[("pending", "Pending"), ("approved", "Approved / applied"),
                         ("rejected", "Rejected"), ("cancelled", "Cancelled")],
            ),
        ),
        migrations.AddField(
            model_name="stockapprovalrequest", name="cancelled_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                related_name="cancelled_stock_approval_requests", blank=True, null=True,
            ),
        ),
        migrations.AddField(
            model_name="stockapprovalrequest", name="cancellation_reason",
            field=models.CharField(max_length=500, blank=True),
        ),
    ]
