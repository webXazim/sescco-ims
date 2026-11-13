"""U05 company expense classification and standalone task expense ledger."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project_pulse", "0003_weighted_progress"),
        ("accounts", "0021_project_pulse_u05_expense_authority"),
    ]
    operations = [
        migrations.CreateModel(
            name="PulseExpenseCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.SlugField(max_length=120, allow_unicode=True, blank=True)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("archived_at", models.DateTimeField(null=True, blank=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                     related_name="pulse_expense_categories", to="projects.project")),
                ("created_by", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                     related_name="pulse_expense_categories_created", to="accounts.companymembership")),
            ],
            options={"ordering": ("sort_order", "name", "pk")},
        ),
        migrations.AddConstraint(model_name="pulseexpensecategory", constraint=models.UniqueConstraint(
            fields=("project", "code"), name="pulse_exp_cat_proj_code_uniq")),
        migrations.AddIndex(model_name="pulseexpensecategory", index=models.Index(
            fields=("project", "archived_at"), name="pulse_exp_cat_proj_active_idx")),
        migrations.CreateModel(
            name="PulseExpenseEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=240)),
                ("amount", models.DecimalField(max_digits=14, decimal_places=2)),
                ("expense_date", models.DateField(default=django.utils.timezone.localdate, db_index=True)),
                ("supplier_name", models.CharField(max_length=160, blank=True)),
                ("reference", models.CharField(max_length=120, blank=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("voided_at", models.DateTimeField(null=True, blank=True, db_index=True)),
                ("void_reason", models.CharField(max_length=240, blank=True)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                     related_name="expense_entries", to="project_pulse.pulsetask")),
                ("expense_category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                     related_name="expense_entries", to="project_pulse.pulseexpensecategory")),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                     related_name="pulse_expenses_recorded", to="accounts.companymembership")),
                ("updated_by", models.ForeignKey(blank=True, null=True,
                     on_delete=django.db.models.deletion.SET_NULL, related_name="pulse_expenses_edited", to="accounts.companymembership")),
                ("voided_by", models.ForeignKey(blank=True, null=True,
                     on_delete=django.db.models.deletion.SET_NULL, related_name="pulse_expenses_voided", to="accounts.companymembership")),
            ],
            options={"ordering": ("-expense_date", "-pk")},
        ),
        migrations.AddConstraint(model_name="pulseexpenseentry", constraint=models.CheckConstraint(
            condition=models.Q(amount__gt=0), name="pulse_expense_amount_gt_zero")),
        migrations.AddIndex(model_name="pulseexpenseentry", index=models.Index(
            fields=("task", "voided_at"), name="pulse_exp_task_void_idx")),
        migrations.AddIndex(model_name="pulseexpenseentry", index=models.Index(
            fields=("expense_category", "expense_date"), name="pulse_exp_cat_date_idx")),
        migrations.CreateModel(
            name="PulseExpenseChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=12, choices=[("created", "Recorded"), ("updated", "Edited"), ("voided", "Voided")])),
                ("before", models.JSONField(default=dict, blank=True)),
                ("after", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="changes", to="project_pulse.pulseexpenseentry")),
                ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="pulse_expense_changes", to="accounts.companymembership")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddIndex(model_name="pulseexpensechange", index=models.Index(
            fields=("entry", "-created_at"), name="pulse_exp_change_date_idx")),
    ]
