"""Execution schedule upgrade: completion-only calculation and secure UI."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.core.models import Company
from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.projects.models import Project
from apps.project_pulse.models import PulseTask, PulseWorkCategory, PulseProgressUpdate
from apps.project_pulse.progress_services import calculate_progress, record_progress
from apps.project_pulse.work_services import save_category, save_task


@override_settings(SECURE_SSL_REDIRECT=False)
class ExecutionScheduleTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Schedule test", slug="pulse-schedule-test")
        self.user = get_user_model().objects.create_user(username="scheduleowner", password="TemporaryTestPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="SCHEDULE", name="Project schedule")
        self.client.force_login(self.user)

    def new_category(self, name):
        return save_category(actor=self.owner, project_id=self.project.pk, data={"name": name})

    def new_work(self, cat, name):
        return save_task(actor=self.owner, project_id=self.project.pk, data={"category": cat, "title": name})

    def test_empty_new_category_zero_and_form_hides_weight(self):
        url = reverse("project_pulse:category_new", args=[self.project.code])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="progress_weight"')
        self.assertEqual(self.client.post(url, {"name":"Mobilization", "description":"Before work", "sort_order":0}).status_code, 302)
        category = PulseWorkCategory.objects.get(project=self.project, name="Mobilization")
        self.assertEqual(category.progress_weight, Decimal("1.00"))
        projects, categories = calculate_progress([self.project.pk])
        self.assertEqual(categories[category.pk]["percent"], Decimal("0.0"))
        self.assertEqual(projects[self.project.pk]["percent"], Decimal("0.0"))
        self.assertContains(self.client.get(reverse("project_pulse:category_detail", args=[self.project.code, category.pk])), "0%")

    def test_completed_work_counts_and_reopen_audited(self):
        cat = self.new_category("Installation")
        work1 = self.new_work(cat, "Equipment installation")
        work2 = self.new_work(cat, "Inspection")
        empty = self.new_category("Testing")
        # A legacy partial update must not count as completion.
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=work1.pk,
                        status="in_progress", progress_percent=80, note="Partial progress")
        _, categories = calculate_progress([self.project.pk])
        self.assertEqual(categories[cat.pk]["percent"], Decimal("0.0"))
        url = reverse("project_pulse:task_completion", args=[self.project.code, work1.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"action":"complete"}).status_code, 302)
        projects, categories = calculate_progress([self.project.pk])
        self.assertEqual(categories[cat.pk]["percent"], Decimal("50.0"))
        self.assertEqual(categories[empty.pk]["percent"], Decimal("0.0"))
        self.assertEqual(projects[self.project.pk]["percent"], Decimal("25.0"))
        self.assertEqual(self.client.post(url, {"action":"reopen"}).status_code, 302)
        work1.refresh_from_db()
        self.assertEqual(work1.status, PulseTask.Status.NOT_STARTED)
        self.assertEqual(work1.progress_percent, 0)
        self.assertEqual(PulseProgressUpdate.objects.filter(task=work1).count(), 3)

    def test_schedule_screen_and_financial_linkage_preserved(self):
        cat = self.new_category("Mobilization")
        work = self.new_work(cat, "Site access")
        listing = self.client.get(reverse("project_pulse:execution_schedule", args=[self.project.code]))
        self.assertContains(listing, "Execution schedule")
        detail = self.client.get(reverse("project_pulse:category_detail", args=[self.project.code, cat.pk]))
        self.assertContains(detail, "Site access")
        self.assertContains(detail, reverse("project_pulse:task_expenses", args=[self.project.code, work.pk]))
        self.assertNotContains(self.client.get(reverse("project_pulse:task_new", args=[self.project.code])), 'name="assigned_to"')
        self.assertNotContains(self.client.get(reverse("project_pulse:task_new", args=[self.project.code])), 'name="progress_weight"')
        homepage = self.client.get(reverse("project_pulse:home"))
        self.assertNotContains(homepage, "My Tasks")
