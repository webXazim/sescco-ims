"""U03 adds project work categories and operational tasks; zero financial fields."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("project_pulse", "0001_project_team"),
        ("accounts", "0019_project_pulse_u03_tasks_authority"),
    ]
    operations = [
        migrations.CreateModel(
            name="PulseWorkCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.SlugField(max_length=120, allow_unicode=True, blank=True)),
                ("description", models.TextField(blank=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("archived_at", models.DateTimeField(blank=True, null=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pulse_categories_created", to="accounts.companymembership")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pulse_work_categories", to="projects.project")),
            ],
            options={"ordering": ("sort_order", "name", "pk")},
        ),
        migrations.AddConstraint(model_name="pulseworkcategory", constraint=models.UniqueConstraint(fields=("project", "code"), name="pulse_cat_project_code_uniq")),
        migrations.AddIndex(model_name="pulseworkcategory", index=models.Index(fields=["project", "archived_at"], name="pulse_cat_project_archive_idx")),
        migrations.CreateModel(
            name="PulseTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("priority", models.CharField(max_length=12, choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")], default="normal")),
                ("status", models.CharField(max_length=20, choices=[("not_started", "Not started"), ("in_progress", "In progress"), ("blocked", "Blocked"), ("on_hold", "On hold"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="not_started")),
                ("planned_start", models.DateField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True, db_index=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("archived_at", models.DateTimeField(blank=True, null=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pulse_assigned_tasks", to="accounts.companymembership")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="project_pulse.pulseworkcategory")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pulse_tasks_created", to="accounts.companymembership")),
            ],
            options={"ordering": ("sort_order", "due_date", "pk")},
        ),
        migrations.AddIndex(model_name="pulsetask", index=models.Index(fields=["category", "archived_at", "status"], name="pulse_task_cat_state_idx")),
        migrations.AddIndex(model_name="pulsetask", index=models.Index(fields=["assigned_to", "archived_at", "due_date"], name="pulse_task_assignee_due_idx")),
    ]
