import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_platform_core"),
        ("projects", "0004_shared_project_authority"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManpowerSupplier",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=200)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], db_index=True, default="active", max_length=20)),
                ("contact_person", models.CharField(blank=True, max_length=160)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("cr_number", models.CharField(blank=True, max_length=60)),
                ("vat_number", models.CharField(blank=True, max_length=60)),
                ("payment_terms", models.CharField(blank=True, max_length=160)),
                ("address", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rental_manpower_manpowersupplier_records",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "rental_manpower_supplier", "ordering": ("code", "name")},
        ),
        migrations.CreateModel(
            name="RentalWorker",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("worker_number", models.CharField(max_length=40)),
                ("full_name", models.CharField(max_length=200)),
                ("national_id", models.CharField(blank=True, max_length=50)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], db_index=True, default="active", max_length=20)),
                ("notes", models.TextField(blank=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rental_manpower_rentalworker_records",
                        to="core.company",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="workers",
                        to="rental_manpower.manpowersupplier",
                    ),
                ),
            ],
            options={"db_table": "rental_worker", "ordering": ("worker_number", "full_name")},
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="rntl_sup_code_uniq"),
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.UniqueConstraint(fields=("company", "name"), name="rntl_sup_name_uniq"),
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.UniqueConstraint(condition=~Q(cr_number=""), fields=("company", "cr_number"), name="rntl_sup_cr_uniq"),
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.UniqueConstraint(condition=~Q(vat_number=""), fields=("company", "vat_number"), name="rntl_sup_vat_uniq"),
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.CheckConstraint(condition=Q(status__in=["active", "inactive"]), name="rntl_sup_status_chk"),
        ),
        migrations.AddIndex(
            model_name="manpowersupplier",
            index=models.Index(fields=["company", "status", "name"], name="rntl_sup_status_name_idx"),
        ),
        migrations.AddConstraint(
            model_name="rentalworker",
            constraint=models.UniqueConstraint(fields=("company", "worker_number"), name="rntl_wrk_number_uniq"),
        ),
        migrations.AddConstraint(
            model_name="rentalworker",
            constraint=models.UniqueConstraint(condition=~Q(national_id=""), fields=("company", "national_id"), name="rntl_wrk_national_id_uniq"),
        ),
        migrations.AddConstraint(
            model_name="rentalworker",
            constraint=models.CheckConstraint(condition=Q(status__in=["active", "inactive"]), name="rntl_wrk_status_chk"),
        ),
        migrations.AddIndex(
            model_name="rentalworker",
            index=models.Index(fields=["company", "status", "full_name"], name="rntl_wrk_status_name_idx"),
        ),
        migrations.AddIndex(
            model_name="rentalworker",
            index=models.Index(fields=["company", "supplier", "status"], name="rntl_wrk_supplier_status_idx"),
        ),
    ]
