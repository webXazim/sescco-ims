# Generated for the document snapshot domain.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.serializers.json
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_platform_core"),
        ("accounts", "0004_backfill_initial_company_access"),
        ("internal_payroll", "0005_salary_payments"),
        ("rental_manpower", "0004_rental_settlements"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workspace", models.CharField(choices=[("internal", "Internal Company"), ("rental", "Rental Manpower")], db_index=True, max_length=16)),
                ("document_type", models.CharField(choices=[("salary_slip", "Salary Slip"), ("internal_timesheet", "Internal Timesheet"), ("salary_payment_receipt", "Salary Payment Receipt"), ("rental_timesheet", "Rental Timesheet"), ("supplier_settlement", "Supplier Settlement"), ("supplier_invoice", "Supplier Invoice"), ("supplier_payment_receipt", "Supplier Payment Receipt")], db_index=True, max_length=32)),
                ("document_number", models.CharField(max_length=48)),
                ("status", models.CharField(choices=[("final", "Final")], default="final", max_length=12)),
                ("period_start", models.DateField(blank=True, db_index=True, null=True)),
                ("title", models.CharField(max_length=240)),
                ("entity_reference", models.CharField(blank=True, max_length=80)),
                ("entity_name", models.CharField(blank=True, max_length=240)),
                ("source_model", models.CharField(max_length=120)),
                ("source_id", models.UUIDField()),
                ("source_reference", models.CharField(blank=True, max_length=80)),
                ("external_reference", models.CharField(blank=True, max_length=120)),
                ("snapshot", models.JSONField(encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("source_fingerprint", models.CharField(max_length=64)),
                ("snapshot_fingerprint", models.CharField(max_length=64)),
                ("finalized_at", models.DateTimeField()),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="documents_businessdocument_records", to="core.company")),
                ("finalized_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="finalized_payroll_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "documents_business_document", "ordering": ("-finalized_at", "-created_at")},
        ),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.UniqueConstraint(fields=("company", "document_number"), name="doc_company_number_uniq")),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.UniqueConstraint(fields=("company", "document_type", "source_model", "source_id"), name="doc_source_type_uniq")),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.UniqueConstraint(condition=~models.Q(external_reference=""), fields=("company", "document_type", "entity_reference", "external_reference"), name="doc_external_ref_uniq")),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.CheckConstraint(condition=models.Q(("workspace__in", ["internal", "rental"])), name="doc_workspace_valid")),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.CheckConstraint(condition=models.Q(("document_type__in", ["salary_slip", "internal_timesheet", "salary_payment_receipt", "rental_timesheet", "supplier_settlement", "supplier_invoice", "supplier_payment_receipt"])), name="doc_type_valid")),
        migrations.AddConstraint(model_name="businessdocument", constraint=models.CheckConstraint(condition=models.Q(("status", "final")), name="doc_status_final")),
        migrations.AddIndex(model_name="businessdocument", index=models.Index(fields=["company", "workspace", "-period_start"], name="doc_workspace_period_idx")),
        migrations.AddIndex(model_name="businessdocument", index=models.Index(fields=["company", "document_type", "-finalized_at"], name="doc_type_time_idx")),
        migrations.AddIndex(model_name="businessdocument", index=models.Index(fields=["company", "source_model", "source_id"], name="doc_source_lookup_idx")),
    ]
