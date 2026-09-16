from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_sourcing_audit_area"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourcingMaterial",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(editable=False, max_length=200)),
                ("category", models.CharField(blank=True, max_length=120)),
                ("default_unit", models.CharField(blank=True, max_length=40)),
                ("aliases", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingmaterial_records", to="core.company")),
            ],
            options={
                "db_table": "sourcing_material",
                "ordering": ("category", "name", "code"),
            },
        ),
        migrations.CreateModel(
            name="SourcingSettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("default_currency", models.CharField(default="SAR", max_length=3)),
                ("fresh_for_days", models.PositiveSmallIntegerField(default=7)),
                ("stale_after_days", models.PositiveSmallIntegerField(default=30)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingsettings_records", to="core.company")),
            ],
            options={"db_table": "sourcing_settings"},
        ),
        migrations.CreateModel(
            name="SourcingTrade",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(editable=False, max_length=200)),
                ("category", models.CharField(blank=True, max_length=120)),
                ("aliases", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingtrade_records", to="core.company")),
            ],
            options={
                "db_table": "sourcing_trade",
                "ordering": ("category", "name", "code"),
            },
        ),
        migrations.CreateModel(
            name="SourcingVendor",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], db_index=True, default="active", max_length=16)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("archived_reason", models.CharField(blank=True, max_length=300)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("purge_after", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("deletion_reason", models.CharField(blank=True, max_length=500)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(editable=False, max_length=200)),
                ("display_name", models.CharField(blank=True, max_length=200)),
                ("primary_contact_name", models.CharField(blank=True, max_length=160)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("mobile", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("region", models.CharField(blank=True, max_length=120)),
                ("cr_number", models.CharField(blank=True, max_length=60)),
                ("vat_number", models.CharField(blank=True, max_length=60)),
                ("website", models.URLField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("last_verified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingvendor_records", to="core.company")),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_sourcingvendor_deleted_records", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "sourcing_vendor",
                "ordering": ("name", "code"),
            },
        ),
        migrations.CreateModel(
            name="SourcingManpowerSupplier",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], db_index=True, default="active", max_length=16)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("archived_reason", models.CharField(blank=True, max_length=300)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("purge_after", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("deletion_reason", models.CharField(blank=True, max_length=500)),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(editable=False, max_length=200)),
                ("primary_contact_name", models.CharField(blank=True, max_length=160)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("mobile", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("city", models.CharField(blank=True, max_length=120)),
                ("region", models.CharField(blank=True, max_length=120)),
                ("cr_number", models.CharField(blank=True, max_length=60)),
                ("vat_number", models.CharField(blank=True, max_length=60)),
                ("notes", models.TextField(blank=True)),
                ("last_verified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingmanpowersupplier_records", to="core.company")),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_sourcingmanpowersupplier_deleted_records", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "sourcing_manpower_supplier",
                "ordering": ("name", "code"),
            },
        ),
        migrations.CreateModel(
            name="SourcingVendorOffer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rate", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("currency", models.CharField(default="SAR", max_length=3)),
                ("rate_valid_until", models.DateField(blank=True, null=True)),
                ("specification", models.CharField(blank=True, max_length=240)),
                ("brand", models.CharField(blank=True, max_length=120)),
                ("model", models.CharField(blank=True, max_length=120)),
                ("available_quantity", models.DecimalField(blank=True, decimal_places=3, max_digits=18, null=True)),
                ("unit", models.CharField(blank=True, max_length=40)),
                ("minimum_quantity", models.DecimalField(blank=True, decimal_places=3, max_digits=18, null=True)),
                ("availability", models.CharField(choices=[("available", "Available"), ("limited", "Limited"), ("unavailable", "Unavailable"), ("unknown", "Unknown")], db_index=True, default="unknown", max_length=16)),
                ("lead_time", models.CharField(blank=True, max_length=120)),
                ("last_verified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("verification_note", models.CharField(blank=True, max_length=500)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingvendoroffer_records", to="core.company")),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vendor_offers", to="sourcing.sourcingmaterial")),
                ("vendor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="supply_offers", to="sourcing.sourcingvendor")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_vendor_offers_verified", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "sourcing_vendor_offer",
                "ordering": ("vendor__name", "material__name", "specification", "brand", "model"),
            },
        ),
        migrations.CreateModel(
            name="SourcingWorkforceOffer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rate", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("currency", models.CharField(default="SAR", max_length=3)),
                ("rate_valid_until", models.DateField(blank=True, null=True)),
                ("available_quantity", models.PositiveIntegerField(blank=True, null=True)),
                ("availability", models.CharField(choices=[("available", "Available"), ("limited", "Limited"), ("unavailable", "Unavailable"), ("unknown", "Unknown")], db_index=True, default="unknown", max_length=16)),
                ("rate_basis", models.CharField(choices=[("hour", "Hour"), ("day", "Day"), ("month", "Month")], default="month", max_length=12)),
                ("overtime_rate", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("mobilization_lead_time", models.CharField(blank=True, max_length=120)),
                ("work_location", models.CharField(blank=True, max_length=160)),
                ("last_verified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("verification_note", models.CharField(blank=True, max_length=500)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingworkforceoffer_records", to="core.company")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="workforce_offers", to="sourcing.sourcingmanpowersupplier")),
                ("trade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="supplier_offers", to="sourcing.sourcingtrade")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_workforce_offers_verified", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "sourcing_workforce_offer",
                "ordering": ("supplier__name", "trade__name"),
            },
        ),
        migrations.CreateModel(
            name="SourcingVendorOfferRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("offer_id_snapshot", models.UUIDField(db_index=True)),
                ("vendor_id_snapshot", models.UUIDField(db_index=True)),
                ("material_id_snapshot", models.UUIDField(db_index=True)),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                ("verified_at", models.DateTimeField(db_index=True)),
                ("contact_name", models.CharField(blank=True, max_length=160)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_vendor_offer_revisions", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingvendorofferrevision_records", to="core.company")),
                ("offer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revisions", to="sourcing.sourcingvendoroffer")),
            ],
            options={
                "db_table": "sourcing_vendor_offer_revision",
                "ordering": ("-verified_at", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="SourcingWorkforceOfferRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("offer_id_snapshot", models.UUIDField(db_index=True)),
                ("supplier_id_snapshot", models.UUIDField(db_index=True)),
                ("trade_id_snapshot", models.UUIDField(db_index=True)),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                ("verified_at", models.DateTimeField(db_index=True)),
                ("contact_name", models.CharField(blank=True, max_length=160)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_workforce_offer_revisions", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sourcing_sourcingworkforceofferrevision_records", to="core.company")),
                ("offer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revisions", to="sourcing.sourcingworkforceoffer")),
            ],
            options={
                "db_table": "sourcing_workforce_offer_revision",
                "ordering": ("-verified_at", "-created_at"),
            },
        ),
        migrations.AddConstraint(
            model_name="sourcingsettings",
            constraint=models.UniqueConstraint(fields=("company",), name="src_settings_company_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingsettings",
            constraint=models.CheckConstraint(condition=Q(fresh_for_days__gte=1), name="src_settings_fresh_positive_ck"),
        ),
        migrations.AddConstraint(
            model_name="sourcingsettings",
            constraint=models.CheckConstraint(condition=Q(stale_after_days__gt=models.F("fresh_for_days")), name="src_settings_stale_after_fresh_ck"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmaterial",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="src_material_company_code_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmaterial",
            constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_material_company_name_uq"),
        ),
        migrations.AddIndex(
            model_name="sourcingmaterial",
            index=models.Index(fields=["company", "is_active", "normalized_name"], name="src_material_active_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmaterial",
            index=models.Index(fields=["company", "category", "normalized_name"], name="src_material_cat_name_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcingtrade",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="src_trade_company_code_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingtrade",
            constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_trade_company_name_uq"),
        ),
        migrations.AddIndex(
            model_name="sourcingtrade",
            index=models.Index(fields=["company", "is_active", "normalized_name"], name="src_trade_active_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingtrade",
            index=models.Index(fields=["company", "category", "normalized_name"], name="src_trade_cat_name_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendor",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="src_vendor_company_code_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendor",
            constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_vendor_company_name_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendor",
            constraint=models.UniqueConstraint(condition=~Q(cr_number=""), fields=("company", "cr_number"), name="src_vendor_company_cr_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendor",
            constraint=models.UniqueConstraint(condition=~Q(vat_number=""), fields=("company", "vat_number"), name="src_vendor_company_vat_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendor",
            constraint=models.CheckConstraint(condition=Q(status__in=["active", "inactive"]), name="src_vendor_status_ck"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendor",
            index=models.Index(fields=["company", "status", "normalized_name"], name="src_vendor_status_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendor",
            index=models.Index(fields=["company", "deleted_at", "normalized_name"], name="src_vendor_trash_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendor",
            index=models.Index(fields=["company", "last_verified_at"], name="src_vendor_verified_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowersupplier",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="src_mps_company_code_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowersupplier",
            constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_mps_company_name_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowersupplier",
            constraint=models.UniqueConstraint(condition=~Q(cr_number=""), fields=("company", "cr_number"), name="src_mps_company_cr_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowersupplier",
            constraint=models.UniqueConstraint(condition=~Q(vat_number=""), fields=("company", "vat_number"), name="src_mps_company_vat_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingmanpowersupplier",
            constraint=models.CheckConstraint(condition=Q(status__in=["active", "inactive"]), name="src_mps_status_ck"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowersupplier",
            index=models.Index(fields=["company", "status", "normalized_name"], name="src_mps_status_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowersupplier",
            index=models.Index(fields=["company", "deleted_at", "normalized_name"], name="src_mps_trash_name_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmanpowersupplier",
            index=models.Index(fields=["company", "last_verified_at"], name="src_mps_verified_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendoroffer",
            constraint=models.UniqueConstraint(fields=("company", "vendor", "material", "specification", "brand", "model"), name="src_vendor_offer_identity_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendoroffer",
            constraint=models.CheckConstraint(condition=Q(available_quantity__isnull=True) | Q(available_quantity__gte=0), name="src_vendor_offer_qty_nonneg_ck"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendoroffer",
            constraint=models.CheckConstraint(condition=Q(minimum_quantity__isnull=True) | Q(minimum_quantity__gte=0), name="src_vendor_offer_min_nonneg_ck"),
        ),
        migrations.AddConstraint(
            model_name="sourcingvendoroffer",
            constraint=models.CheckConstraint(condition=Q(rate__isnull=True) | Q(rate__gte=0), name="src_vendor_offer_rate_nonneg_ck"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=["company", "material", "availability", "is_active"], name="src_offer_material_find_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=["company", "vendor", "is_active"], name="src_offer_vendor_active_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=["company", "last_verified_at"], name="src_offer_verified_idx"),
        ),
        migrations.AddConstraint(
            model_name="sourcingworkforceoffer",
            constraint=models.UniqueConstraint(fields=("company", "supplier", "trade"), name="src_workforce_offer_identity_uq"),
        ),
        migrations.AddConstraint(
            model_name="sourcingworkforceoffer",
            constraint=models.CheckConstraint(condition=Q(rate__isnull=True) | Q(rate__gte=0), name="src_workforce_rate_nonneg_ck"),
        ),
        migrations.AddConstraint(
            model_name="sourcingworkforceoffer",
            constraint=models.CheckConstraint(condition=Q(overtime_rate__isnull=True) | Q(overtime_rate__gte=0), name="src_workforce_ot_nonneg_ck"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=["company", "trade", "availability", "is_active"], name="src_workforce_trade_find_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=["company", "supplier", "is_active"], name="src_workforce_supplier_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=["company", "last_verified_at"], name="src_workforce_verified_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendorofferrevision",
            index=models.Index(fields=["company", "offer_id_snapshot", "-verified_at"], name="src_offer_rev_offer_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendorofferrevision",
            index=models.Index(fields=["company", "vendor_id_snapshot", "-verified_at"], name="src_offer_rev_vendor_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceofferrevision",
            index=models.Index(fields=["company", "offer_id_snapshot", "-verified_at"], name="src_work_rev_offer_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceofferrevision",
            index=models.Index(fields=["company", "supplier_id_snapshot", "-verified_at"], name="src_work_rev_supplier_idx"),
        ),
    ]
