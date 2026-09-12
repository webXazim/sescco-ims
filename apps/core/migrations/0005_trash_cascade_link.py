from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_company_document_branding_lineage_repair"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrashCascadeLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("root_type", models.CharField(db_index=True, max_length=120)),
                ("root_id", models.CharField(db_index=True, max_length=64)),
                ("child_type", models.CharField(db_index=True, max_length=120)),
                ("child_id", models.CharField(db_index=True, max_length=64)),
                ("reason", models.CharField(blank=True, max_length=500)),
                ("restored_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trash_cascade_links", to="core.company")),
                ("deleted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trash_cascade_links_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "core_trash_cascade_link",
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="trashcascadelink",
            constraint=models.UniqueConstraint(
                condition=models.Q(restored_at__isnull=True),
                fields=("company", "root_type", "root_id", "child_type", "child_id"),
                name="core_trash_cascade_active_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="trashcascadelink",
            index=models.Index(fields=["company", "root_type", "root_id", "restored_at"], name="core_trash_cascade_root_idx"),
        ),
        migrations.AddIndex(
            model_name="trashcascadelink",
            index=models.Index(fields=["company", "child_type", "child_id", "restored_at"], name="core_trash_cascade_child_idx"),
        ),
    ]
