import uuid

import django.core.serializers.json
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("legal_name", models.CharField(blank=True, max_length=250)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "verbose_name_plural": "companies",
                "db_table": "core_company",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="CompanySettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("timezone", models.CharField(default="Asia/Riyadh", max_length=64)),
                ("currency_code", models.CharField(default="SAR", max_length=3)),
                ("country_code", models.CharField(default="SA", max_length=2)),
                (
                    "company",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="settings",
                        to="core.company",
                    ),
                ),
            ],
            options={"verbose_name_plural": "company settings", "db_table": "core_company_settings"},
        ),
        migrations.CreateModel(
            name="NumberSequence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(max_length=80)),
                ("prefix", models.CharField(blank=True, max_length=24)),
                ("padding", models.PositiveSmallIntegerField(default=6, validators=[django.core.validators.MinValueValidator(1)])),
                ("next_value", models.PositiveBigIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ("last_issued_value", models.PositiveBigIntegerField(default=0)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="number_sequences",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "core_number_sequence", "ordering": ("company__name", "key")},
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("area", models.CharField(choices=[
                    ("access", "Access"), ("core", "Platform Core"), ("projects", "Projects"),
                    ("inventory", "Inventory"), ("data_exchange", "Data Exchange"),
                    ("internal", "Internal Payroll"), ("rental", "Rental Manpower"),
                    ("documents", "Documents"), ("management", "Management"),
                ], db_index=True, max_length=20)),
                ("action", models.CharField(db_index=True, max_length=100)),
                ("object_type", models.CharField(db_index=True, max_length=120)),
                ("object_id", models.CharField(db_index=True, max_length=64)),
                ("object_label", models.CharField(blank=True, max_length=240)),
                ("actor_membership_id", models.UUIDField(blank=True, null=True)),
                ("actor_role", models.CharField(blank=True, max_length=40)),
                ("actor_username", models.CharField(blank=True, max_length=150)),
                ("actor_display_name", models.CharField(blank=True, max_length=300)),
                ("actor_email", models.EmailField(blank=True, max_length=254)),
                ("before", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("after", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("metadata", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("request_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_events",
                        to="core.company",
                    ),
                ),
            ],
            options={"db_table": "core_audit_event", "ordering": ("-created_at", "-id")},
        ),
        migrations.AddConstraint(
            model_name="numbersequence",
            constraint=models.UniqueConstraint(fields=("company", "key"), name="core_seq_company_key_uniq"),
        ),
        migrations.AddConstraint(
            model_name="numbersequence",
            constraint=models.CheckConstraint(condition=models.Q(next_value__gt=0), name="core_seq_next_positive"),
        ),
        migrations.AddConstraint(
            model_name="numbersequence",
            constraint=models.CheckConstraint(condition=models.Q(padding__gt=0), name="core_seq_pad_positive"),
        ),
        migrations.AddIndex(
            model_name="numbersequence",
            index=models.Index(fields=["company", "key"], name="core_sequence_lookup_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["company", "-created_at"], name="core_audit_company_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["company", "area", "-created_at"], name="core_audit_area_time_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["company", "object_type", "object_id"], name="core_audit_object_idx"),
        ),
    ]
