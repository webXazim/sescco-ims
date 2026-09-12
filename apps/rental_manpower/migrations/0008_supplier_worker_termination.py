from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("rental_manpower", "0007_master_trash_retention"),
    ]

    operations = [
        migrations.AddField(
            model_name="manpowersupplier",
            name="inactive_on",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="manpowersupplier",
            name="inactive_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="manpowersupplier",
            name="terminated_on",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="manpowersupplier",
            name="termination_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="rentalworker",
            name="terminated_on",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="rentalworker",
            name="termination_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.RemoveConstraint(
            model_name="manpowersupplier",
            name="rntl_sup_status_chk",
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["active", "inactive", "terminated"]),
                name="rntl_sup_status_chk",
            ),
        ),
        migrations.AddConstraint(
            model_name="manpowersupplier",
            constraint=models.CheckConstraint(
                condition=~Q(status="terminated") | Q(terminated_on__isnull=False),
                name="rntl_sup_terminated_date_chk",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="rentalworker",
            name="rntl_wrk_status_chk",
        ),
        migrations.AddConstraint(
            model_name="rentalworker",
            constraint=models.CheckConstraint(
                condition=Q(status__in=["active", "inactive", "terminated"]),
                name="rntl_wrk_status_chk",
            ),
        ),
        migrations.AddConstraint(
            model_name="rentalworker",
            constraint=models.CheckConstraint(
                condition=~Q(status="terminated") | Q(terminated_on__isnull=False),
                name="rntl_wrk_terminated_date_chk",
            ),
        ),
        migrations.AlterField(
            model_name="manpowersupplier",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("inactive", "Inactive"), ("terminated", "Terminated")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="rentalworker",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("inactive", "Inactive"), ("terminated", "Terminated")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
    ]
