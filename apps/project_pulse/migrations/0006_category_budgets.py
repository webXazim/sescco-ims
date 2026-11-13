"""Append-only approved budget revisions per work category."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("project_pulse", "0005_expense_approvals_payments_evidence"),
                    ("accounts", "0023_project_pulse_u07_budget_authority")]
    operations = [
        migrations.CreateModel(name="PulseBudgetRevision", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("revision_number", models.PositiveIntegerField()),
            ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
            ("reason", models.CharField(max_length=500)),
            ("status", models.CharField(max_length=10, default="pending", choices=[
                ("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected")])),
            ("submitted_at", models.DateTimeField(auto_now_add=True)),
            ("reviewed_at", models.DateTimeField(null=True, blank=True)),
            ("review_note", models.CharField(max_length=500, blank=True)),
            ("category", models.ForeignKey(to="project_pulse.pulseworkcategory", on_delete=django.db.models.deletion.PROTECT, related_name="budget_revisions")),
            ("submitted_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, related_name="pulse_budgets_submitted")),
            ("reviewed_by", models.ForeignKey(to="accounts.companymembership", on_delete=django.db.models.deletion.PROTECT, null=True, blank=True, related_name="pulse_budgets_reviewed")),
        ], options={"ordering": ("-revision_number", "-pk")}),
        migrations.AddConstraint(model_name="pulsebudgetrevision", constraint=models.UniqueConstraint(
            fields=("category", "revision_number"), name="pulse_budget_cat_rev_unique")),
        migrations.AddConstraint(model_name="pulsebudgetrevision", constraint=models.UniqueConstraint(
            fields=("category",), condition=models.Q(status="pending"), name="pulse_budget_one_pending")),
        migrations.AddConstraint(model_name="pulsebudgetrevision", constraint=models.CheckConstraint(
            condition=models.Q(amount__gte=0), name="pulse_budget_amount_nonnegative")),
        migrations.AddConstraint(model_name="pulsebudgetrevision", constraint=models.CheckConstraint(
            condition=models.Q(revision_number__gt=0), name="pulse_budget_rev_positive")),
        migrations.AddIndex(model_name="pulsebudgetrevision", index=models.Index(
            fields=("category", "status", "-revision_number"), name="pulse_budget_cat_status_idx")),
    ]
