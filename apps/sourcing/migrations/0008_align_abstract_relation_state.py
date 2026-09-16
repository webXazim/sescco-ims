# Generated for SESCCO MS 1.0.113 migration-state alignment.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_platform_core"),
        ("sourcing", "0007_rename_manpower_contact_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="sourcingmanpowercontact",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingmanpowersupplier",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingmanpowersupplier",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_deleted_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="sourcingmaterial",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingsettings",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingtrade",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingvendor",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingvendor",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(app_label)s_%(class)s_deleted_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="sourcingvendorcontact",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingvendoroffer",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingvendorofferrevision",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingworkforceoffer",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
        migrations.AlterField(
            model_name="sourcingworkforceofferrevision",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_records",
                to="core.company",
            ),
        ),
    ]
