"""U03 company-scope, approvals separation, task/category history and permissions."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import Company, AuditEvent
from apps.projects.models import Project
from apps.project_pulse.forms import PulseTaskForm
from apps.project_pulse.models import PulseTask, PulseWorkCategory
from apps.project_pulse.services import assign_team_member, remove_team_member
from apps.project_pulse.work_services import (save_category, save_task, set_category_archive,
                                              set_task_archive)

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class WorkCategoryTaskTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="U03 Company", slug="u03-company")
        self.other_company = Company.objects.create(name="U03 Other", slug="u03-other")
        self.owner_user = User.objects.create_user(username="u03-owner", password="TestStrong!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="U03-01", name="Civil Site Work")
        self.second = Project.objects.create(company=self.company, code="U03-02", name="Second Site Work")
        self.foreign = Project.objects.create(company=self.other_company, code="U03-99", name="Secret Project")

    def member(self, username, *, perms=None, scope=ScopeMode.ALL, projects=()):
        if perms is None:
            perms = ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view")
        user = get_user_model().objects.create_user(username=username, password="TestStrong!2026")
        profile = AccessProfile.objects.create(company=self.company, key=f"custom-{username}", name=username)
        for perm in perms:
            AccessProfilePermission.objects.create(profile=profile, permission=perm)
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM,
            access_profile=profile, project_scope_mode=scope,
        )
        if scope == ScopeMode.SELECTED:
            for project in projects:
                membership.project_scopes.create(project=project)
        return user, membership

    def category(self, name="Civil Works", project=None):
        return save_category(actor=self.owner, project_id=(project or self.project).pk,
                             data={"name": name, "description": "Site operations", "sort_order": 0})

    def task_data(self, category, **overrides):
        data = {"category": category, "title": "Excavation", "description": "Earthworks",
                "assigned_to": None, "priority": "high", "status": "not_started",
                "planned_start": None, "due_date": None, "sort_order": 0}
        data.update(overrides)
        return data

    def test_permissions_registered_and_owner_only_default(self):
        for code in (AccessPermission.PULSE_CATEGORIES_VIEW, AccessPermission.PULSE_CATEGORIES_MANAGE,
                     AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_TASKS_MANAGE):
            self.assertTrue(membership_has_permission(self.owner, code))
            self.assertIn(code.value, {r["code"] for r in permission_catalog()})
        for perms in (["pulse.tasks.manage"], ["pulse.overview.view", "pulse.tasks.view"]):
            with self.assertRaises(ValidationError):
                _clean_permissions(perms)
        self.assertEqual(len(_clean_permissions(["pulse.overview.view", "pulse.projects.view",
            "pulse.tasks.view", "pulse.tasks.manage"])), 4)

    def test_owner_creates_category_task_and_updates_via_http(self):
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.post(reverse("project_pulse:category_new", args=[self.project.code]),
            {"name": "Civil Works", "sort_order": 3, "description": "Road works"}).status_code, 302)
        category = PulseWorkCategory.objects.get(project=self.project)
        self.assertEqual(category.code, "civil-works")
        task_response = self.client.post(reverse("project_pulse:task_new", args=[self.project.code]), {
            "category": category.pk, "title": "Excavation", "priority": "critical", "status": "in_progress",
            "description": "Safe excavations", "sort_order": 1, "due_date": "2026-12-01",
        })
        self.assertEqual(task_response.status_code, 302, task_response.content.decode()[:300])
        task = PulseTask.objects.get(category=category)
        self.assertEqual(task.status, PulseTask.Status.IN_PROGRESS)
        self.assertEqual(task.priority, PulseTask.Priority.CRITICAL)
        self.assertIsNone(task.assigned_to)
        self.assertContains(self.client.get(reverse("project_pulse:tasks", args=[self.project.code])), "Excavation")
        self.assertContains(self.client.get(reverse("project_pulse:categories", args=[self.project.code])), "Civil Works")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="pulse.task.created").exists())
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="pulse.category.created").exists())
        self.assertIsNone(self.project.inventory_manager_id)

    def test_task_assignment_requires_authorized_project_team_member_with_task_view(self):
        category = self.category()
        _, eligible = self.member("u03-worker", perms=("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"))
        _, viewless = self.member("u03-no-task", perms=("pulse.overview.view", "pulse.projects.view"))
        assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=eligible.pk, role="member")
        assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=viewless.pk, role="member")
        task = save_task(actor=self.owner, project_id=self.project.pk,
                         data=self.task_data(category, assigned_to=eligible))
        self.assertEqual(task.assigned_to, eligible)
        with self.assertRaises(ValidationError):
            save_task(actor=self.owner, project_id=self.project.pk,
                      data=self.task_data(category, title="Not allowed", assigned_to=viewless))
        _, not_on_team = self.member("u03-untagged")
        with self.assertRaises(ValidationError):
            save_task(actor=self.owner, project_id=self.project.pk,
                      data=self.task_data(category, title="Not team", assigned_to=not_on_team))
        self.client.force_login(eligible.user)
        self.assertContains(self.client.get(reverse("project_pulse:my_tasks")), "Excavation")
        team_record = eligible.pulse_project_assignments.get(project=self.project)
        remove_team_member(actor=self.owner, project_id=self.project.pk, team_member_id=team_record.pk)
        self.assertNotContains(self.client.get(reverse("project_pulse:my_tasks")), "Excavation")

    def test_company_scope_and_cross_project_category_injection_blocked(self):
        other_category = self.category(name="Other Job", project=self.second)
        outsider_category = save_category(actor=self.owner, project_id=self.project.pk,
                                 data={"name": "Civil", "description": "", "sort_order": 0})
        with self.assertRaises(ValidationError):
            save_task(actor=self.owner, project_id=self.project.pk,
                      data=self.task_data(other_category))
        user, scoped = self.member("u03-scoped", perms=("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view", "pulse.tasks.manage"),
                                  scope=ScopeMode.SELECTED, projects=(self.project,))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:tasks", args=[self.second.code])).status_code, 404)
        self.assertEqual(self.client.get(reverse("project_pulse:tasks", args=[self.foreign.code])).status_code, 404)
        self.assertEqual(self.client.post(reverse("project_pulse:task_new", args=[self.project.code]), {
            "category": other_category.pk, "title": "Injected", "priority": "high", "status": "not_started"
        }).status_code, 200)
        self.assertFalse(PulseTask.objects.filter(title="Injected").exists())
        with self.assertRaises(PermissionDenied):
            save_task(actor=scoped, project_id=self.second.pk,
                      data=self.task_data(other_category))
        self.assertEqual(outsider_category.project, self.project)

    def test_separate_category_and_task_permissions(self):
        category = self.category()
        cat_perms = ("pulse.overview.view", "pulse.projects.view", "pulse.categories.view", "pulse.categories.manage")
        task_perms = ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view", "pulse.tasks.manage")
        cat_user, _ = self.member("u03-category-admin", perms=cat_perms)
        task_user, _ = self.member("u03-task-admin", perms=task_perms)
        self.client.force_login(cat_user)
        self.assertEqual(self.client.get(reverse("project_pulse:categories", args=[self.project.code])).status_code, 200)
        self.assertEqual(self.client.post(reverse("project_pulse:task_new", args=[self.project.code])).status_code, 403)
        self.client.force_login(task_user)
        self.assertEqual(self.client.get(reverse("project_pulse:tasks", args=[self.project.code])).status_code, 200)
        self.assertEqual(self.client.post(reverse("project_pulse:category_new", args=[self.project.code])).status_code, 403)
        task_response = self.client.post(reverse("project_pulse:task_new", args=[self.project.code]), {
            "category": category.pk, "title": "Allowed", "priority": "normal", "status": "not_started",
            "description": "", "assigned_to": "", "planned_start": "", "due_date": "",
            "sort_order": 0, "progress_weight": "1.00",
        })
        if task_response.status_code != 302:
            # Include real form errors in the next staging run instead of a
            # mysterious '200 != 302' assertion with no validation context.
            errors = (task_response.context["form"].errors.as_json()
                      if task_response.context and "form" in task_response.context else
                      task_response.content.decode(errors="replace")[:500])
            self.fail(f"Task form returned {task_response.status_code}: {errors}")

    def test_validation_duplicate_category_due_date_and_wrong_member(self):
        category = self.category()
        with self.assertRaises(ValidationError):
            self.category(name="Civil Works")
        with self.assertRaises(ValidationError):
            save_task(actor=self.owner, project_id=self.project.pk,
                      data=self.task_data(category, planned_start="2026-12-08", due_date="2026-12-01"))
        # Service uses model clean, which must reject invalid date data even without forms.
        self.assertEqual(PulseTask.objects.count(), 0)

    def test_archive_restore_preserves_tasks_and_categories(self):
        category = self.category()
        task = save_task(actor=self.owner, project_id=self.project.pk, data=self.task_data(category))
        with self.assertRaises(ValidationError):
            set_category_archive(actor=self.owner, project_id=self.project.pk, category_id=category.pk, archive=True)
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=task.pk, archive=True)
        set_category_archive(actor=self.owner, project_id=self.project.pk, category_id=category.pk, archive=True)
        with self.assertRaises(ValidationError):
            set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=task.pk, archive=False)
        set_category_archive(actor=self.owner, project_id=self.project.pk, category_id=category.pk, archive=False)
        set_task_archive(actor=self.owner, project_id=self.project.pk, task_id=task.pk, archive=False)
        task.refresh_from_db()
        category.refresh_from_db()
        self.assertIsNone(task.archived_at)
        self.assertIsNone(category.archived_at)
        self.assertEqual(PulseTask.objects.count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action="pulse.task.restored").exists())

    def test_archive_still_works_after_assignee_access_revocation(self):
        category = self.category()
        _, member = self.member("u03-former-team")
        record = assign_team_member(actor=self.owner, project_id=self.project.pk,
                                    member_id=member.pk, role="member")
        task = save_task(actor=self.owner, project_id=self.project.pk,
                         data=self.task_data(category, assigned_to=member))
        remove_team_member(actor=self.owner, project_id=self.project.pk,
                           team_member_id=record.pk)
        set_task_archive(actor=self.owner, project_id=self.project.pk,
                         task_id=task.pk, archive=True)
        task.refresh_from_db()
        self.assertIsNotNone(task.archived_at)
        with self.assertRaises(ValidationError):
            set_task_archive(actor=self.owner, project_id=self.project.pk,
                             task_id=task.pk, archive=False)

    def test_inactive_project_readonly_operations_and_forms(self):
        category = self.category()
        Project.objects.filter(pk=self.project.pk).update(status=Project.Status.ON_HOLD)
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("project_pulse:category_new", args=[self.project.code])).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:task_new", args=[self.project.code])).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:tasks", args=[self.project.code])).status_code, 200)
        with self.assertRaises(ValidationError):
            save_task(actor=self.owner, project_id=self.project.pk, data=self.task_data(category))
        self.assertFalse(PulseTask.objects.exists())

    def test_task_management_does_not_grant_budget_or_inventory_access(self):
        # The financial permission must exist in the global catalog, but an
        # operational task-only profile must never inherit it or stock access.
        _, member = self.member("u03-tasks-not-finance", perms=(
            "pulse.overview.view", "pulse.projects.view",
            "pulse.tasks.view", "pulse.tasks.manage",
        ))
        self.assertFalse(membership_has_permission(member, AccessPermission.PULSE_FINANCIALS_VIEW))
        self.assertFalse(membership_has_permission(member, AccessPermission.PULSE_BUDGETS_VIEW))
        self.assertFalse(membership_has_permission(member, AccessPermission.INVENTORY_STOCK_VIEW))
        self.assertFalse(hasattr(PulseTask, "expense"))
        self.assertFalse(hasattr(PulseWorkCategory, "approved_budget"))

    def test_all_task_pages_require_explicit_permissions(self):
        user, _ = self.member("u03-project-only", perms=("pulse.overview.view", "pulse.projects.view"))
        self.client.force_login(user)
        for name in ("tasks", "categories"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"project_pulse:{name}",
                    args=[self.project.code])).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:my_tasks")).status_code, 403)

    def test_task_archive_filter_and_post_only_actions(self):
        category = self.category()
        task = save_task(actor=self.owner, project_id=self.project.pk,
                         data=self.task_data(category))
        self.client.force_login(self.owner_user)
        url = reverse("project_pulse:task_archive", args=[self.project.code, task.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"action": "invalid"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"action": "archive"}).status_code, 302)
        listing_url = reverse("project_pulse:tasks", args=[self.project.code])
        self.assertNotContains(self.client.get(listing_url), "Excavation")
        self.assertContains(self.client.get(listing_url + "?archived=1"), "Excavation")

    def test_task_edit_changes_status_and_due_date(self):
        category = self.category()
        task = save_task(actor=self.owner, project_id=self.project.pk,
                         data=self.task_data(category))
        self.client.force_login(self.owner_user)
        resp = self.client.post(reverse("project_pulse:task_edit", args=[self.project.code, task.pk]), {
            "category": category.pk, "title": "Excavation Phase 2", "description": "Follow-up",
            "priority": "low", "status": "blocked", "due_date": "2026-12-15", "sort_order": 2,
        })
        self.assertEqual(resp.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.title, "Excavation Phase 2")
        self.assertEqual(task.status, PulseTask.Status.BLOCKED)
        self.assertEqual(task.due_date.isoformat(), "2026-12-15")
        self.assertTrue(AuditEvent.objects.filter(action="pulse.task.updated").exists())
