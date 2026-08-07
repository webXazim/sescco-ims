import uuid
from decimal import Decimal

import apps.inventory.models
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_seed_common_units"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "reference",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("idempotency_key", models.UUIDField(editable=False, unique=True)),
                (
                    "movement_type",
                    models.CharField(
                        choices=[
                            ("opening", "Opening stock"),
                            ("addition", "Stock added"),
                            ("usage", "Stock used"),
                            ("adjustment_in", "Positive adjustment"),
                            ("adjustment_out", "Negative adjustment"),
                            ("reversal", "Reversal"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=16,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.001"))
                        ],
                    ),
                ),
                (
                    "previous_balance",
                    models.DecimalField(decimal_places=3, max_digits=16),
                ),
                (
                    "new_balance",
                    models.DecimalField(decimal_places=3, max_digits=16),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=16,
                        null=True,
                    ),
                ),
                ("movement_date", models.DateField()),
                ("invoice_reference", models.CharField(blank=True, max_length=120)),
                ("purpose", models.CharField(blank=True, max_length=180)),
                ("recipient", models.CharField(blank=True, max_length=180)),
                ("reason", models.CharField(blank=True, max_length=240)),
                ("notes", models.TextField(blank=True)),
                (
                    "attachment",
                    models.FileField(
                        blank=True,
                        upload_to="stock-movements/%Y/%m/",
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=("pdf", "jpg", "jpeg", "png")
                            ),
                            apps.inventory.models.validate_attachment_size,
                        ],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_movements_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reversal_of",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="inventory.stockmovement",
                    ),
                ),
                (
                    "stock_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="inventory.stockitem",
                    ),
                ),
            ],
            options={
                "ordering": ("-movement_date", "-created_at", "-pk"),
                "indexes": [
                    models.Index(
                        fields=["stock_item", "-movement_date", "-created_at"],
                        name="movement_item_date_idx",
                    ),
                    models.Index(
                        fields=["movement_type", "-movement_date"],
                        name="movement_type_date_idx",
                    ),
                    models.Index(
                        fields=["invoice_reference"],
                        name="movement_reference_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gt", 0)),
                        name="movement_quantity_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("previous_balance__gte", 0)),
                        name="movement_previous_balance_nonnegative",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("new_balance__gte", 0)),
                        name="movement_new_balance_nonnegative",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("unit_price__isnull", True), ("unit_price__gte", 0), _connector="OR"),
                        name="movement_unit_price_nonnegative",
                    ),
                ],
            },
        ),
    ]
