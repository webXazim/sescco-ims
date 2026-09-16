from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sourcing", "0005_trade_alias_search")]

    operations = [
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=("company", "is_active", "material", "last_verified_at"), name="src_offer_mat_verify_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=("company", "is_active", "vendor", "last_verified_at"), name="src_offer_vnd_verify_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingvendoroffer",
            index=models.Index(fields=("company", "is_active", "availability", "last_verified_at"), name="src_offer_avail_ver_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=("company", "is_active", "trade", "last_verified_at"), name="src_work_trade_ver_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=("company", "is_active", "supplier", "last_verified_at"), name="src_work_sup_ver_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingworkforceoffer",
            index=models.Index(fields=("company", "is_active", "availability", "last_verified_at"), name="src_work_avail_ver_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingmaterial",
            index=models.Index(fields=("company", "is_active", "category", "normalized_name"), name="src_mat_scale_find_idx"),
        ),
        migrations.AddIndex(
            model_name="sourcingtrade",
            index=models.Index(fields=("company", "is_active", "category", "normalized_name"), name="src_trade_scale_find_idx"),
        ),
    ]
