"""U08 immutable contract revisions, approved variations and remaining cost forecasts."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def common_fields():
    return [
        ("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID")),
        ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
        ("reason", models.CharField(max_length=500)),
        ("status", models.CharField(max_length=10, default="pending", db_index=True,
                    choices=[("pending", "Pending review"), ("approved", "Approved"), ("rejected", "Rejected")])),
        ("submitted_at", models.DateTimeField(auto_now_add=True)),
        ("reviewed_at", models.DateTimeField(null=True, blank=True)),
        ("review_note", models.CharField(max_length=500, blank=True)),
        ("project", models.ForeignKey(to="projects.project", on_delete=django.db.models.deletion.PROTECT)),
        ("submitted_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, related_name="+")),
        ("reviewed_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT,
                                         related_name="+", null=True, blank=True)),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("project_pulse", "0006_category_budgets"),
        ("accounts", "0024_project_pulse_u08_commercial_authority"),
    ]
    operations = [
        migrations.CreateModel(name="PulseContractRevision", fields=common_fields(),
                               options={"ordering": ("-submitted_at", "-pk")}),
        migrations.CreateModel(name="PulseContractVariation", fields=common_fields()+[
            ("description", models.CharField(max_length=220)),
            ("reference", models.CharField(max_length=100, blank=True)),
        ], options={"ordering": ("-submitted_at", "-pk")}),
        migrations.CreateModel(name="PulseCostForecast", fields=common_fields()+[
            ("as_of_date", models.DateField(default=django.utils.timezone.localdate)),
            ("actual_cost_basis", models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                help_text="Approved project expenses at the time this forecast was approved.")),
        ], options={"ordering": ("-submitted_at", "-pk")}),
        migrations.AddConstraint(model_name="pulsecontractrevision", constraint=models.UniqueConstraint(
            fields=("project",), condition=models.Q(status="pending"), name="pulse_contract_one_pending")),
        migrations.AddConstraint(model_name="pulsecontractrevision", constraint=models.CheckConstraint(
            condition=models.Q(amount__gte=0), name="pulse_contract_nonnegative")),
        migrations.AddConstraint(model_name="pulsecontractvariation", constraint=models.CheckConstraint(
            condition=~models.Q(amount=0), name="pulse_variation_nonzero")),
        migrations.AddConstraint(model_name="pulsecostforecast", constraint=models.UniqueConstraint(
            fields=("project",), condition=models.Q(status="pending"), name="pulse_forecast_one_pending")),
        migrations.AddConstraint(model_name="pulsecostforecast", constraint=models.CheckConstraint(
            condition=models.Q(amount__gte=0), name="pulse_forecast_nonnegative")),
    ]
