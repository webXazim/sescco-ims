"""U04 regression/security cases. Run: python manage.py test apps.project_pulse."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.projects.models import Project
from apps.project_pulse.models import PulseTask, PulseWorkCategory, PulseProgressUpdate
from apps.project_pulse.progress_services import calculate_progress, can_update_task_progress, record_progress
from apps.project_pulse.services import assign_team_member, remove_team_member
from apps.project_pulse.work_services import save_category, save_task, set_task_archive


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class PulseProgressTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="U04 Company", slug="u04-company")
        other = Company.objects.create(name="U04 Other", slug="u04-other")
        self.user = User.objects.create_user(username="u04owner", password="SecureTest!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="U04-01", name="Road Construction")
        self.other_project = Project.objects.create(company=self.company, code="U04-02", name="Other Project")
        self.foreign_project = Project.objects.create(company=other, code="U04-99", name="Other Company Work")

    def category(self, name="Civil", project=None, weight=None):
        details = {"name": name, "description": "", "sort_order": 0}
        if weight is not None:
            details["progress_weight"] = Decimal(weight)
        return save_category(actor=self.owner, project_id=(project or self.project).pk, data=details)

    def task(self, category, name="Excavate", weight=None, assignee=None, status="not_started"):
        details = {"category": category, "title": name, "description": "", "assigned_to": assignee,
                   "priority": "normal", "status": status, "planned_start": None,
                   "due_date": None, "sort_order": 0}
        if weight is not None:
            details["progress_weight"] = Decimal(weight)
        return save_task(actor=self.owner, project_id=category.project_id, data=details)

    def member(self, username, perms, scope=ScopeMode.ALL, projects=()):
        user = get_user_model().objects.create_user(username=username, password="SecureTest!2026")
        profile = AccessProfile.objects.create(company=self.company, key=f"custom-{username}", name=username)
        for permission in perms:
            AccessProfilePermission.objects.create(profile=profile, permission=permission)
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM,
            access_profile=profile, project_scope_mode=scope,
        )
        if scope == ScopeMode.SELECTED:
            for project in projects:
                membership.project_scopes.create(project=project)
        return user, membership

    def test_owner_permissions_granted_and_profile_requirements(self):
        for permission in (AccessPermission.PULSE_PROGRESS_VIEW, AccessPermission.PULSE_PROGRESS_UPDATE):
            self.assertTrue(membership_has_permission(self.owner, permission))
            self.assertIn(permission.value, {item["code"] for item in permission_catalog()})
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.overview.view", "pulse.projects.view", "pulse.progress.update"])
        allowed = ["pulse.overview.view", "pulse.projects.view", "pulse.tasks.view",
                   "pulse.progress.view", "pulse.progress.update"]
        self.assertEqual(len(_clean_permissions(allowed)), 5)

    def test_weighted_categories_and_projects_use_unrounded_intermediate_values(self):
        civil = self.category(weight="2.00")
        elec = self.category("Electrical", weight="1.00")
        t1 = self.task(civil, weight="2.00")
        t2 = self.task(civil, "Backfill", weight="1.00")
        self.task(elec, "Cable Testing")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=t1.pk,
                        progress_percent=50, status="in_progress", note="Halfway")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=t2.pk,
                        progress_percent=100, status="completed", note="Finished")
        projects, categories = calculate_progress([self.project.pk, self.other_project.pk])
        self.assertEqual(categories[civil.pk]["percent"], Decimal("66.7"))
        self.assertEqual(categories[elec.pk]["percent"], Decimal("0.0"))
        self.assertEqual(projects[self.project.pk]["percent"], Decimal("44.4"))
        self.assertEqual(projects[self.project.pk]["completed_count"], 1)
        self.assertEqual(projects[self.project.pk]["task_count"], 3)
        self.assertFalse(projects[self.other_project.pk]["has_work"])

    def test_cancelled_and_archived_are_excluded_from_denominator(self):
        category = self.category()
        active = self.task(category)
        canceled = self.task(category, "Cancelled")
        archived = self.task(category, "Archived")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=active.pk,
                        progress_percent=70, status="in_progress")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=canceled.pk,
                        progress_percent=20, status="cancelled")
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=archived.pk, archive=True)
        projects, categories = calculate_progress([self.project.pk])
        self.assertEqual(categories[category.pk]["percent"], Decimal("70.0"))
        self.assertEqual(projects[self.project.pk]["task_count"], 1)
        self.assertEqual(projects[self.project.pk]["percent"], Decimal("70.0"))

    def test_empty_category_has_no_influence_and_invalid_weight_rejected(self):
        empty = self.category(name="Empty", weight="99.00")
        active = self.category(name="Working", weight="1.00")
        task = self.task(active)
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=100, status="completed")
        projects, categories = calculate_progress([self.project.pk])
        self.assertFalse(categories[empty.pk]["has_work"])
        self.assertEqual(projects[self.project.pk]["percent"], Decimal("100.0"))
        with self.assertRaises(ValidationError):
            self.category("Invalid", weight="0")
        with self.assertRaises(ValidationError):
            self.task(active, "Invalid weight", weight="0")

    def test_progress_validation_and_immutable_history(self):
        task = self.task(self.category())
        for percentage, status in ((101, "in_progress"), (-1, "in_progress"),
                                   (100, "blocked"), (20, "not_started"), (90, "completed")):
            with self.subTest(percent=percentage, status=status):
                with self.assertRaises(ValidationError):
                    record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                                    progress_percent=percentage, status=status)
        update = record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                                 progress_percent=30, status="in_progress", note="Trenching 30%")
        self.assertEqual(update.previous_percent, 0)
        self.assertEqual(update.new_percent, 30)
        self.assertEqual(update.updated_by, self.owner)
        self.assertEqual(update.note, "Trenching 30%")
        with self.assertRaises(ValidationError):
            update.save()
        with self.assertRaises(ValidationError):
            record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                            progress_percent=30, status="in_progress")
        self.assertTrue(AuditEvent.objects.filter(action="pulse.task.progress_updated").exists())

    def test_legacy_status_editor_records_history_and_normalizes(self):
        category = self.category()
        task = self.task(category)
        details = {"category": category, "title": task.title, "description": "", "assigned_to": None,
                   "priority": "normal", "status": "completed", "planned_start": None,
                   "due_date": None, "sort_order": 0}
        save_task(actor=self.owner, project_id=self.project.pk, data=details, task_id=task.pk)
        task.refresh_from_db()
        self.assertEqual(task.progress_percent, 100)
        save_task(actor=self.owner, project_id=self.project.pk,
                  data={**details, "status": "blocked"}, task_id=task.pk)
        task.refresh_from_db()
        self.assertEqual(task.progress_percent, 0)
        self.assertEqual(list(task.progress_updates.values_list("new_percent", flat=True)), [0, 100])

    def test_assignee_can_update_own_tasks_not_other_tasks_or_scopes(self):
        category = self.category()
        permissions = ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view",
                       "pulse.progress.view", "pulse.progress.update")
        user, member = self.member("u04worker", perms=permissions,
                                   scope=ScopeMode.SELECTED, projects=(self.project,))
        assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        own = self.task(category, assignee=member)
        other = self.task(category, name="Another task")
        self.assertTrue(can_update_task_progress(member, own))
        self.assertFalse(can_update_task_progress(member, other))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, own.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("project_pulse:task_progress_update", args=[self.project.code, own.pk]),
                {"progress_percent": "40", "status": "in_progress", "note": "Excavated"}).status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.progress_percent, 40)
        self.assertEqual(self.client.post(reverse("project_pulse:task_progress_update", args=[self.project.code, other.pk]),
                {"progress_percent": 20, "status": "in_progress"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:task_progress", args=[self.other_project.code, own.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_pulse:task_progress", args=[self.foreign_project.code, own.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_pulse:project_detail", args=[self.other_project.code])).status_code, 404)

    def test_team_role_alone_does_not_grant_permission_and_revoke_blocks(self):
        category = self.category()
        user, member = self.member("u04plain", perms=("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"))
        roster = assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        task = self.task(category, assignee=member)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, task.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("project_pulse:task_progress_update", args=[self.project.code, task.pk]),
            {"progress_percent": 25, "status": "in_progress"}).status_code, 403)
        self.client.force_login(self.user)
        remove_team_member(actor=self.owner, project_id=self.project.pk, team_member_id=roster.pk)
        # Manager still able to manage a task previously assigned to a now-revoked user.
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=25, status="in_progress")
        task.refresh_from_db()
        self.assertEqual(task.progress_percent, 25)

    def test_manager_can_update_all_tasks_with_explicit_progress_permission(self):
        category = self.category()
        task = self.task(category)
        permissions = ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view",
                       "pulse.progress.view", "pulse.progress.update")
        _user, member = self.member("u04projectmanager", perms=permissions)
        assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="manager")
        self.assertTrue(can_update_task_progress(member, task))
        update = record_progress(actor=member, project_id=self.project.pk, task_id=task.pk,
                                 progress_percent=20, status="blocked", note="Waiting for access")
        self.assertEqual(update.new_status, PulseTask.Status.BLOCKED)

    def test_project_on_hold_is_readonly_and_history_remains_visible(self):
        category = self.category()
        task = self.task(category)
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=25, status="in_progress")
        Project.objects.filter(pk=self.project.pk).update(status=Project.Status.ON_HOLD)
        self.client.force_login(self.user)
        response = self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Save progress update")
        with self.assertRaises(ValidationError):
            record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                            progress_percent=50, status="in_progress")

    def test_task_editor_can_complete_and_reopen_without_new_weight_posted(self):
        category = self.category()
        task = self.task(category)
        self.client.force_login(self.user)
        url = reverse("project_pulse:task_edit", args=[self.project.code, task.pk])
        payload = {"category": category.pk, "title": "Excavate", "description": "",
                   "priority": "normal", "status": "completed", "sort_order": 0}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302, response.content.decode()[:200])
        task.refresh_from_db()
        self.assertEqual(task.progress_percent, 100)
        self.assertEqual(task.status, PulseTask.Status.COMPLETED)
        response = self.client.post(url, {**payload, "status": "blocked"})
        self.assertEqual(response.status_code, 302, response.content.decode()[:200])
        task.refresh_from_db()
        self.assertEqual(task.progress_percent, 0)
        self.assertEqual(task.progress_updates.count(), 2)

    def test_progress_note_only_and_archived_task_readonly(self):
        category = self.category()
        task = self.task(category)
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=0, status="not_started", note="Work front unavailable")
        self.assertEqual(task.progress_updates.count(), 1)
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=task.pk, archive=True)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, task.pk])).status_code, 200)
        response = self.client.post(reverse("project_pulse:task_progress_update", args=[self.project.code, task.pk]),
            {"progress_percent": 10, "status": "in_progress"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PulseProgressUpdate.objects.filter(task=task).count(), 1)

    def test_progress_is_not_financial_and_project_dashboard_scoped(self):
        category = self.category()
        task = self.task(category)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("project_pulse:project_detail", args=[self.project.code])), "Physical work progress")
        self.assertContains(self.client.get(reverse("project_pulse:tasks", args=[self.project.code])), "0%")
        self.assertFalse(hasattr(task, "expense"))
        self.assertFalse(hasattr(category, "approved_budget"))
