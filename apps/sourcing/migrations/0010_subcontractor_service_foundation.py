"""Additive reference-only subcontractor schema. No operational table changes."""
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def _base():
    return [
        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
        ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_records", to="core.company")),
    ]


def _lifecycle():
    return _base() + [
        ("status", models.CharField(max_length=16, choices=[("active", "Active"), ("inactive", "Inactive")], default="active", db_index=True)),
        ("archived_at", models.DateTimeField(null=True, blank=True, db_index=True)),
        ("archived_reason", models.CharField(max_length=300, blank=True)),
        ("deleted_at", models.DateTimeField(null=True, blank=True, db_index=True)),
        ("purge_after", models.DateTimeField(null=True, blank=True, db_index=True)),
        ("deletion_reason", models.CharField(max_length=500, blank=True)),
        ("deleted_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(app_label)s_%(class)s_deleted_records")),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0009_vendor_profile_structure"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="SourcingSubcontractor",
            fields=_lifecycle() + [
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(max_length=200, editable=False)),
                ("display_name", models.CharField(max_length=200, blank=True)),
                ("primary_contact_name", models.CharField(max_length=160, blank=True)),
                ("company_phone", models.CharField(max_length=40, blank=True)),
                ("company_email", models.EmailField(blank=True)),
                ("mobile", models.CharField(max_length=40, blank=True)),
                ("email", models.EmailField(blank=True)),
                ("address", models.CharField(max_length=255, blank=True)),
                ("street_number", models.CharField(max_length=40, blank=True)),
                ("district", models.CharField(max_length=120, blank=True)),
                ("city", models.CharField(max_length=120, blank=True)),
                ("region", models.CharField(max_length=120, blank=True)),
                ("postal_code", models.CharField(max_length=20, blank=True)),
                ("service_coverage", models.CharField(max_length=255, blank=True)),
                ("cr_number", models.CharField(max_length=60, blank=True)),
                ("vat_number", models.CharField(max_length=60, blank=True)),
                ("website", models.URLField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("last_verified_at", models.DateTimeField(null=True, blank=True, db_index=True)),
            ],
            options={"db_table": "sourcing_subcontractor", "ordering": ("normalized_name", "code")},
        ),
        migrations.CreateModel(
            name="SourcingService",
            fields=_base() + [
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=200)),
                ("normalized_name", models.CharField(max_length=200, editable=False)),
                ("category", models.CharField(max_length=120, blank=True)),
                ("default_rate_basis", models.CharField(max_length=24, choices=[("hour", "Hour"), ("day", "Day"), ("visit", "Visit"), ("job", "Job"), ("m2", "Square metre"), ("m3", "Cubic metre"), ("month", "Month"), ("quotation", "Quotation")], blank=True)),
                ("aliases", models.JSONField(default=list, blank=True)),
                ("normalized_aliases", models.TextField(blank=True, editable=False)),
                ("description", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True, db_index=True)),
            ],
            options={"db_table": "sourcing_service", "ordering": ("category", "normalized_name", "code")},
        ),
        migrations.CreateModel(
            name="SourcingSubcontractorContact",
            fields=_base() + [
                ("subcontractor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contacts", to="sourcing.sourcingsubcontractor")),
                ("salutation", models.CharField(max_length=20, blank=True)),
                ("first_name", models.CharField(max_length=100)),
                ("last_name", models.CharField(max_length=100, blank=True)),
                ("designation", models.CharField(max_length=120, blank=True)),
                ("department", models.CharField(max_length=120, blank=True)),
                ("email", models.EmailField(blank=True)),
                ("work_phone", models.CharField(max_length=40, blank=True)),
                ("mobile", models.CharField(max_length=40, blank=True)),
                ("is_primary", models.BooleanField(default=False, db_index=True)),
                ("is_active", models.BooleanField(default=True, db_index=True)),
            ],
            options={"db_table": "sourcing_subcontractor_contact", "ordering": ("-is_primary", "first_name", "last_name", "id")},
        ),
        migrations.CreateModel(
            name="SourcingSubcontractorService",
            fields=_base() + [
                ("subcontractor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_offers", to="sourcing.sourcingsubcontractor")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subcontractor_offers", to="sourcing.sourcingservice")),
                ("scope_description", models.CharField(max_length=300, blank=True)),
                ("service_location", models.CharField(max_length=160, blank=True)),
                ("availability", models.CharField(max_length=16, choices=[("available", "Available"), ("limited", "Limited"), ("unavailable", "Unavailable"), ("unknown", "Unknown")], default="unknown", db_index=True)),
                ("rate", models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)),
                ("currency", models.CharField(max_length=3, default="SAR")),
                ("rate_valid_until", models.DateField(null=True, blank=True)),
                ("rate_basis", models.CharField(max_length=24, choices=[("hour", "Hour"), ("day", "Day"), ("visit", "Visit"), ("job", "Job"), ("m2", "Square metre"), ("m3", "Cubic metre"), ("month", "Month"), ("quotation", "Quotation")], default="quotation")),
                ("lead_time", models.CharField(max_length=120, blank=True)),
                ("last_verified_at", models.DateTimeField(null=True, blank=True, db_index=True)),
                ("verified_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_subcontractor_services_verified")),
                ("verification_note", models.CharField(max_length=500, blank=True)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True, db_index=True)),
            ],
            options={"db_table": "sourcing_subcontractor_service", "ordering": ("subcontractor__normalized_name", "service__normalized_name", "scope_description")},
        ),
        migrations.CreateModel(
            name="SourcingSubcontractorServiceRevision",
            fields=_base() + [
                ("offer", models.ForeignKey(to="sourcing.sourcingsubcontractorservice", null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revisions")),
                ("offer_id_snapshot", models.UUIDField(db_index=True)),
                ("subcontractor_id_snapshot", models.UUIDField(db_index=True)),
                ("service_id_snapshot", models.UUIDField(db_index=True)),
                ("before", models.JSONField(default=dict, blank=True)),
                ("after", models.JSONField(default=dict, blank=True)),
                ("verified_at", models.DateTimeField(db_index=True)),
                ("actor", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_subcontractor_service_revisions")),
                ("contact_name", models.CharField(max_length=160, blank=True)),
                ("note", models.CharField(max_length=500, blank=True)),
            ],
            options={"db_table": "sourcing_subcontractor_service_revision", "ordering": ("-verified_at", "-created_at")},
        ),
        migrations.AddConstraint(model_name="sourcingsubcontractor", constraint=models.UniqueConstraint(fields=("company", "code"), name="src_subco_company_code_uq")),
        migrations.AddConstraint(model_name="sourcingsubcontractor", constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_subco_company_name_uq")),
        migrations.AddConstraint(model_name="sourcingsubcontractor", constraint=models.UniqueConstraint(fields=("company", "cr_number"), condition=~Q(cr_number=""), name="src_subco_company_cr_uq")),
        migrations.AddConstraint(model_name="sourcingsubcontractor", constraint=models.UniqueConstraint(fields=("company", "vat_number"), condition=~Q(vat_number=""), name="src_subco_company_vat_uq")),
        migrations.AddConstraint(model_name="sourcingsubcontractor", constraint=models.CheckConstraint(condition=Q(status__in=["active", "inactive"]), name="src_subco_status_ck")),
        migrations.AddIndex(model_name="sourcingsubcontractor", index=models.Index(fields=("company", "status", "normalized_name"), name="src_subco_status_name_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractor", index=models.Index(fields=("company", "deleted_at", "normalized_name"), name="src_subco_trash_name_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractor", index=models.Index(fields=("company", "last_verified_at"), name="src_subco_verified_idx")),
        migrations.AddConstraint(model_name="sourcingsubcontractorcontact", constraint=models.UniqueConstraint(fields=("subcontractor",), condition=Q(is_primary=True, is_active=True), name="src_subco_primary_contact_uq")),
        migrations.AddIndex(model_name="sourcingsubcontractorcontact", index=models.Index(fields=("company", "subcontractor", "is_active"), name="src_subco_contact_active_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractorcontact", index=models.Index(fields=("company", "email"), name="src_subco_contact_email_idx")),
        migrations.AddConstraint(model_name="sourcingservice", constraint=models.UniqueConstraint(fields=("company", "code"), name="src_service_company_code_uq")),
        migrations.AddConstraint(model_name="sourcingservice", constraint=models.UniqueConstraint(fields=("company", "normalized_name"), name="src_service_company_name_uq")),
        migrations.AddIndex(model_name="sourcingservice", index=models.Index(fields=("company", "is_active", "normalized_name"), name="src_service_active_name_idx")),
        migrations.AddIndex(model_name="sourcingservice", index=models.Index(fields=("company", "category", "normalized_name"), name="src_service_category_idx")),
        migrations.AddConstraint(model_name="sourcingsubcontractorservice", constraint=models.UniqueConstraint(fields=("company", "subcontractor", "service", "scope_description", "service_location"), name="src_subservice_identity_uq")),
        migrations.AddConstraint(model_name="sourcingsubcontractorservice", constraint=models.CheckConstraint(condition=Q(rate__isnull=True) | Q(rate__gte=0), name="src_subservice_rate_nonneg_ck")),
        migrations.AddIndex(model_name="sourcingsubcontractorservice", index=models.Index(fields=("company", "service", "availability", "is_active"), name="src_subsvc_service_find_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractorservice", index=models.Index(fields=("company", "subcontractor", "is_active"), name="src_subsvc_subco_active_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractorservice", index=models.Index(fields=("company", "last_verified_at"), name="src_subsvc_verified_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractorservicerevision", index=models.Index(fields=("company", "offer_id_snapshot", "-verified_at"), name="src_subsvc_rev_offer_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractorservicerevision", index=models.Index(fields=("company", "subcontractor_id_snapshot", "-verified_at"), name="src_subsvc_rev_subco_idx")),
    ]
