"""Upgrade 4: user-facing work navigation and work-field availability.

These are genuine Django integration tests and must be run on a staging DB.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.work_services import save_category, save_task


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class WorkProgressUiUpgradeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Work UI", slug="work-ui-u4")
        user = get_user_model().objects.create_user(
            username="workuiowner", password="U4TemporaryTestingOnly2026!"
        )
        self.actor = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.OWNER
        )
        self.project = Project.objects.create(
            company=self.company, code="WORKUI", name="Work UI Test Project"
        )
        self.client.force_login(user)

    def test_canonical_urls_and_existing_aliases(self):
        code = self.project.code
        self.assertEqual(reverse("project_pulse:work_progress", args=[code]), f"/app/project-pulse/projects/{code}/work-progress/")
        self.assertEqual(reverse("project_pulse:works", args=[code]), f"/app/project-pulse/projects/{code}/works/")
        for name in ("work_progress", "works", "execution_schedule", "scheduled_works"):
            response = self.client.get(reverse(f"project_pulse:{name}", args=[code]))
            self.assertEqual(response.status_code, 200)
        page = self.client.get(reverse("project_pulse:work_progress", args=[code]))
        self.assertContains(page, "Work Progress")
        self.assertContains(page, "Work Categories")
        self.assertContains(page, "Import Works")

    def test_work_columns_and_search_by_serial_and_unit(self):
        category = save_category(actor=self.actor, project_id=self.project.pk, data={"name": "Cable Installation"})
        work = save_task(actor=self.actor, project_id=self.project.pk, data={
            "category": category, "serial_number": "2.1.3", "title": "Install MV cables",
            "unit": "LM", "quantity": "540",
        })
        url = reverse("project_pulse:works", args=[self.project.code])
        page = self.client.get(url)
        self.assertContains(page, "2.1.3")
        self.assertContains(page, "Install MV cables")
        self.assertContains(page, "540")
        self.assertContains(page, "Unit")
        self.assertContains(self.client.get(url, {"q": "2.1.3"}), "Install MV cables")
        self.assertContains(self.client.get(url, {"q": "LM"}), "Install MV cables")
        self.assertNotContains(self.client.get(url, {"q": "No such work"}), "Install MV cables")
        detail = self.client.get(reverse("project_pulse:category_detail", args=[self.project.code, category.pk]))
        self.assertContains(detail, "Update %")
        form = self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, work.pk]))
        self.assertContains(form, "Save Progress")
        self.assertContains(form, 'type="range"')

    def test_category_search_and_name_only_form(self):
        save_category(actor=self.actor, project_id=self.project.pk, data={"name": "Transformer Installation"})
        save_category(actor=self.actor, project_id=self.project.pk, data={"name": "Cable Installation"})
        page = self.client.get(reverse("project_pulse:work_progress", args=[self.project.code]), {"q": "Cable"})
        self.assertContains(page, "Cable Installation")
        self.assertNotContains(page, "Transformer Installation")
        form = self.client.get(reverse("project_pulse:category_new", args=[self.project.code]))
        self.assertContains(form, 'name="name"')
        self.assertNotContains(form, 'name="description"')
        self.assertNotContains(form, 'name="progress_weight"')
