from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rental_manpower", "0006_supplier_worker_lifecycle"),
    ]

    operations = [
        *[
            migrations.AddField(model_name=model, name="deleted_at", field=models.DateTimeField(blank=True, db_index=True, null=True))
            for model in ("manpowersupplier", "rentalworker")
        ],
        *[
            migrations.AddField(model_name=model, name="purge_after", field=models.DateTimeField(blank=True, db_index=True, null=True))
            for model in ("manpowersupplier", "rentalworker")
        ],
        *[
            migrations.AddField(model_name=model, name="deletion_reason", field=models.CharField(blank=True, max_length=500))
            for model in ("manpowersupplier", "rentalworker")
        ],
        migrations.AddField(
            model_name="manpowersupplier", name="deleted_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rental_suppliers_deleted", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="rentalworker", name="deleted_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rental_workers_deleted", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(model_name="manpowersupplier", index=models.Index(fields=["company", "deleted_at", "name"], name="rntl_sup_trash_name_idx")),
        migrations.AddIndex(model_name="rentalworker", index=models.Index(fields=["company", "deleted_at", "full_name"], name="rntl_wrk_trash_name_idx")),
    ]
