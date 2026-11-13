"""Project Pulse team assignments are independent of Inventory approval managers."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("accounts", "0018_project_pulse_u02_team_authority"),
        ("projects", "0007_inventory_manager"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="PulseProjectTeamMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("manager", "Project manager"), ("member", "Team member")], default="member", max_length=12)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("assigned_at", models.DateTimeField(default=timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pulse_team_changes_made", to="accounts.companymembership")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pulse_project_assignments", to="accounts.companymembership")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pulse_team_members", to="projects.project")),
            ],
            options={"ordering": ("project__code", "role", "membership__user__username")},
        ),
        migrations.AddConstraint(model_name="pulseprojectteammember", constraint=models.UniqueConstraint(
            fields=("project", "membership"), name="pulse_project_membership_unique")),
        migrations.AddConstraint(model_name="pulseprojectteammember", constraint=models.UniqueConstraint(
            condition=models.Q(role="manager", is_active=True), fields=("project",), name="pulse_single_active_manager")),
        migrations.AddIndex(model_name="pulseprojectteammember", index=models.Index(
            fields=["project", "is_active", "role"], name="pulse_team_project_role_idx")),
    ]
