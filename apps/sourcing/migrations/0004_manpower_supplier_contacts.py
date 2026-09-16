from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0003_material_alias_search"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourcingManpowerContact",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("salutation", models.CharField(blank=True, max_length=20)),
                ("first_name", models.CharField(max_length=100)),
                ("last_name", models.CharField(blank=True, max_length=100)),
                ("designation", models.CharField(blank=True, max_length=120)),
                ("department", models.CharField(blank=True, max_length=120)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("work_phone", models.CharField(blank=True, max_length=40)),
                ("mobile", models.CharField(blank=True, max_length=40)),
                ("is_primary", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingmanpowercontact_records", to="core.company")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contacts", to="sourcing.sourcingmanpowersupplier")),
            ],
            options={
                "db_table": "sourcing_manpower_contact",
                "ordering": ("-is_primary", "first_name", "last_name", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowercontact",
            constraint=models.UniqueConstraint(condition=models.Q(("is_active", True), ("is_primary", True)), fields=("supplier",), name="src_mps_one_primary_contact_uq"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowercontact",
            index=models.Index(fields=["company", "supplier", "is_active"], name="src_mpcontact_supplier_active_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowercontact",
            index=models.Index(fields=["company", "email"], name="src_mpcontact_email_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowercontact",
            index=models.Index(fields=["company", "mobile"], name="src_mpcontact_mobile_idx"),
        ),
    ]
