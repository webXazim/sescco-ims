import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("projects", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Unit",
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
                ("name", models.CharField(max_length=80)),
                (
                    "normalized_name",
                    models.CharField(editable=False, max_length=80, unique=True),
                ),
                ("symbol", models.CharField(max_length=20)),
                (
                    "normalized_symbol",
                    models.CharField(editable=False, max_length=20, unique=True),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="StockItem",
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
                ("material_name", models.CharField(max_length=180)),
                (
                    "normalized_material_name",
                    models.CharField(editable=False, max_length=180),
                ),
                ("description", models.TextField(blank=True)),
                ("supplier_name", models.CharField(max_length=180)),
                (
                    "normalized_supplier_name",
                    models.CharField(editable=False, max_length=180),
                ),
                ("supplier_phone", models.CharField(max_length=40)),
                (
                    "normalized_supplier_phone",
                    models.CharField(editable=False, max_length=40),
                ),
                ("supplier_location", models.CharField(blank=True, max_length=180)),
                (
                    "current_quantity",
                    models.DecimalField(decimal_places=3, default=0, max_digits=16),
                ),
                (
                    "minimum_quantity",
                    models.DecimalField(decimal_places=3, default=0, max_digits=16),
                ),
                (
                    "latest_unit_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=16,
                        null=True,
                    ),
                ),
                ("latest_addition_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("archived", "Archived")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_items_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_items",
                        to="projects.project",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_items",
                        to="inventory.unit",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="stock_items_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("project", "material_name", "supplier_name"),
                "indexes": [
                    models.Index(
                        fields=["project", "status", "material_name"],
                        name="stock_project_status_name_idx",
                    ),
                    models.Index(
                        fields=["normalized_supplier_name", "normalized_supplier_phone"],
                        name="stock_supplier_identity_idx",
                    ),
                    models.Index(
                        fields=["latest_addition_date"],
                        name="stock_latest_add_date_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "project",
                            "normalized_material_name",
                            "normalized_supplier_name",
                            "normalized_supplier_phone",
                        ),
                        name="uniq_stock_identity_per_project",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(current_quantity__gte=0),
                        name="stock_current_quantity_nonnegative",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(minimum_quantity__gte=0),
                        name="stock_minimum_quantity_nonnegative",
                    ),
                ],
            },
        ),
    ]
