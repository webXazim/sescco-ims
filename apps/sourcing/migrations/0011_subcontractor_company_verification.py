"""Independent subcontractor company verification (not service price verification)."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def clear_ambiguous_profile_freshness(apps, schema_editor):
    # Prior releases advanced subcontractor.last_verified_at during offer verification.
    # No profile-level verification existed; those timestamps cannot prove company
    # identity was checked. Clearing them prevents false 'Fresh' badges.
    apps.get_model("sourcing", "SourcingSubcontractor").objects.all().update(last_verified_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("sourcing", "0010_subcontractor_service_foundation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SourcingSubcontractorVerificationRevision",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(app_label)s_%(class)s_records", to="core.company")),
                ("subcontractor", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verification_revisions", to="sourcing.sourcingsubcontractor")),
                ("subcontractor_id_snapshot", models.UUIDField(db_index=True)),
                ("before", models.JSONField(default=dict, blank=True)),
                ("after", models.JSONField(default=dict, blank=True)),
                ("verified_at", models.DateTimeField(db_index=True)),
                ("actor", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sourcing_subcontractor_company_verifications", to=settings.AUTH_USER_MODEL)),
                ("contact_name", models.CharField(max_length=160, blank=True)),
                ("note", models.CharField(max_length=500, blank=True)),
            ],
            options={"db_table": "sourcing_subcontractor_verification_revision", "ordering": ("-verified_at", "-created_at")},
        ),
        migrations.AddIndex(
            model_name="sourcingsubcontractorverificationrevision",
            index=models.Index(fields=("company", "subcontractor_id_snapshot", "-verified_at"), name="src_subco_rev_verify_idx"),
        ),
        migrations.RunPython(clear_ambiguous_profile_freshness, migrations.RunPython.noop),
    ]
