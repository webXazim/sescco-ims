from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_movement_identity_snapshots")]
    operations = [
        migrations.AddIndex(model_name="stockitem", index=models.Index(fields=["normalized_material_name"], name="stock_material_norm_idx")),
        migrations.AddIndex(model_name="stockitem", index=models.Index(fields=["current_quantity"], name="stock_quantity_idx")),
        migrations.AddIndex(model_name="stockitem", index=models.Index(fields=["latest_unit_price"], name="stock_latest_price_idx")),
        migrations.AddIndex(model_name="stockitem", index=models.Index(fields=["updated_at"], name="stock_updated_at_idx")),
        migrations.AddIndex(model_name="stockmovement", index=models.Index(fields=["created_by", "-movement_date"], name="movement_user_date_idx")),
        migrations.AddIndex(model_name="stockmovement", index=models.Index(fields=["unit_price"], name="movement_unit_price_idx")),
        migrations.AddIndex(model_name="stockmovement", index=models.Index(fields=["project_code_snapshot"], name="movement_project_snap_idx")),
    ]
