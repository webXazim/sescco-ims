"""Private, tenant-scoped subcontractor qualification document references."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0011_subcontractor_company_verification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SourcingSubcontractorDocument",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_records", to="core.company")),
                ("subcontractor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="qualification_documents", to="sourcing.sourcingsubcontractor")),
                ("kind", models.CharField(max_length=24, choices=[("cr", "Commercial registration"), ("license", "Trade / service license"), ("insurance", "Insurance"), ("tax", "Tax / VAT certificate"), ("safety", "Safety certificate"), ("technical", "Technical qualification"), ("other", "Other qualification")])),
                ("title", models.CharField(max_length=200)),
                ("reference_number", models.CharField(max_length=120, blank=True)),
                ("issuer", models.CharField(max_length=160, blank=True)),
                ("issued_on", models.DateField(null=True, blank=True)),
                ("expires_on", models.DateField(null=True, blank=True, db_index=True)),
                ("notes", models.TextField(blank=True)),
                ("review_status", models.CharField(max_length=16, db_index=True, default="pending", choices=[("pending", "Pending review"), ("approved", "Reviewed / accepted"), ("rejected", "Rejected")])),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("reviewed_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="sourcing_subcontractor_documents_reviewed")),
                ("review_note", models.CharField(max_length=500, blank=True)),
                ("original_name", models.CharField(max_length=255)),
                ("storage_key", models.CharField(max_length=350, unique=True, editable=False)),
                ("content_type", models.CharField(max_length=40, editable=False)),
                ("file_size", models.PositiveIntegerField(editable=False)),
                ("sha256", models.CharField(max_length=64, editable=False)),
            ],
            options={"db_table": "sourcing_subcontractor_document", "ordering": ("expires_on", "title", "id")},
        ),
        migrations.AddIndex(model_name="sourcingsubcontractordocument", index=models.Index(fields=("company", "subcontractor", "expires_on"), name="src_subdoc_expiry_idx")),
        migrations.AddIndex(model_name="sourcingsubcontractordocument", index=models.Index(fields=("company", "review_status"), name="src_subdoc_review_idx")),
    ]
