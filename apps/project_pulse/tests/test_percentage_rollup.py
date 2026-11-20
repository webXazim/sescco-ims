"""Upgrade 2: exact rounding, empty categories, archival, and progress permissions."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.models import PulseProgressUpdate, PulseTask
from apps.project_pulse.progress_services import calculate_progress, record_progress
from apps.project_pulse.work_services import save_category, save_task
from apps.project_pulse.report_services import PulseReportFilterForm, build_report

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=STORAGES)
class PercentageRollupTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="U2 Percent", slug="u2-percent")
        user = get_user_model().objects.create_user(username="u2owner", password="Test!Pass2026")
        self.owner = CompanyMembership.objects.create(company=company, user=user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=company, code="U2-PERCENT", name="Execution")
        self.client.force_login(user)

    def category(self, name):
        return save_category(actor=self.owner, project_id=self.project.pk, data={"name": name})

    def work(self, category, name):
        return save_task(actor=self.owner, project_id=self.project.pk,
                         data={"category": category, "title": name})

    def test_full_precision_project_average_and_one_decimal_rounding(self):
        a = self.category("A")
        b = self.category("B")
        self.category("Empty must be ignored")
        works = [self.work(a, str(i)) for i in range(3)]
        another = self.work(b, "Another")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=works[0].pk,
                        progress_percent=1, status="auto")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=another.pk,
                        progress_percent=30, status="auto")
        totals, cats = calculate_progress([self.project.pk])
        self.assertEqual(cats[a.pk]["percent"], Decimal("0.3"))
        self.assertEqual(cats[b.pk]["percent"], Decimal("30.0"))
        self.assertEqual(totals[self.project.pk]["percent"], Decimal("15.2"))
        self.assertEqual(totals[self.project.pk]["measured_categories"], 2)

    def test_work_edit_preserves_completed_status_and_percentage(self):
        cat = self.category("A")
        task = self.work(cat, "Initial")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=100, status="auto")
        url = reverse("project_pulse:task_edit", args=[self.project.code, task.pk])
        self.assertEqual(self.client.post(url, {"category": cat.pk, "title": "Renamed", "sort_order": 0}).status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, PulseTask.Status.COMPLETED)
        self.assertEqual(task.progress_percent, 100)
        self.assertEqual(PulseProgressUpdate.objects.filter(task=task).count(), 1)

    def test_report_and_screen_show_partial_percentage(self):
        cat = self.category("A")
        task = self.work(cat, "Cable")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=45, status="auto")
        page = self.client.get(reverse("project_pulse:tasks", args=[self.project.code]))
        self.assertContains(page, "45%")
        detail = self.client.get(reverse("project_pulse:task_progress", args=[self.project.code, task.pk]))
        self.assertContains(detail, "45%")
        form = PulseReportFilterForm({"report": "progress"}, project=self.project)
        self.assertTrue(form.is_valid(), form.errors)
        report = build_report(project=self.project, actor=self.owner, filters=form.cleaned_data)
        self.assertEqual(report.rows[0][3], "45%")
        self.assertEqual(dict(report.stats)["Overall project progress"], "45.0%")
