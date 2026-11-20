"""Upgrade 5 release hardening: category identity and reimport safety.

Run with Django/DB configured:
    python manage.py test apps.project_pulse.tests.test_work_import_release_u5
"""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.import_services import parse_workbook
from apps.project_pulse.models import PulseTask, PulseWorkImportBatch
from apps.project_pulse.work_services import save_category, save_task

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def excel_upload(*sections):
    book = Workbook()
    sheet = book.active
    sheet.title = "Works"
    for category, works in sections:
        sheet.append([category])
        sheet.append(["SN", "Description", "Unit", "Quantity", "% Completion"])
        for work in works:
            sheet.append(list(work))
    data = BytesIO()
    book.save(data)
    return SimpleUploadedFile("works.xlsx", data.getvalue())


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=STORAGES)
class WorkImportReleaseU5Tests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="U5 Work Import", slug="u5-work-import")
        self.user = get_user_model().objects.create_user(
            username="u5-work-owner", password="U5TestOnlyPass2026!"
        )
        self.actor = CompanyMembership.objects.create(
            company=company, user=self.user, role=AccessRole.OWNER
        )
        self.project = Project.objects.create(
            company=company, code="U5-WORK", name="U5 Work Test"
        )
        self.client.force_login(self.user)

    def upload(self, *sections):
        return self.client.post(
            reverse("project_pulse:works_import_upload", args=[self.project.code]),
            {"workbook": excel_upload(*sections)},
        )

    def test_blank_percentage_imports_as_zero_and_creates_single_category(self):
        response = self.upload(
            ("Cable Works", [("1", "Lay cable", "LM", 500, None)]),
            ("cable works", [("2", "Terminate cable", "EA", 10, 25)]),
        )
        self.assertEqual(response.status_code, 302)
        batch = PulseWorkImportBatch.objects.get(project=self.project)
        self.assertEqual(batch.category_count, 1)
        self.assertEqual([r["progress"] for r in batch.preview_data["items"]], [0, 25])
        self.assertTrue(batch.preview_data["items"][0]["blank_percent"])
        confirm = self.client.post(reverse(
            "project_pulse:works_import_apply", args=[self.project.code, batch.pk]
        ))
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 2)

    def test_conflicting_excel_category_names_are_rejected_not_merged(self):
        result = parse_workbook(excel_upload(
            ("Civil & Steel", [("1", "Civil work", "EA", 1, None)]),
            ("Civil Steel", [("2", "Steel work", "EA", 1, None)]),
        ))
        self.assertTrue(any("conflicts" in error for error in result["errors"]))
        response = self.upload(
            ("Civil & Steel", [("1", "Civil work", "EA", 1, None)]),
            ("Civil Steel", [("2", "Steel work", "EA", 1, None)]),
        )
        self.assertContains(response, "conflicts")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
        self.assertFalse(PulseTask.objects.exists())

    def test_existing_category_with_different_name_same_code_is_rejected(self):
        save_category(actor=self.actor, project_id=self.project.pk,
                      data={"name": "Civil & Steel"})
        response = self.upload(
            ("Civil Steel", [("1", "New work", "EA", 1, None)]),
        )
        self.assertContains(response, "conflicts with existing Work Category")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
        self.assertFalse(PulseTask.objects.exists())

    def test_ambiguous_case_insensitive_existing_serial_is_rejected(self):
        category = save_category(actor=self.actor, project_id=self.project.pk,
                                 data={"name": "Cable Works"})
        save_task(actor=self.actor, project_id=self.project.pk, data={
            "category": category, "serial_number": "ABC", "title": "Cable one"
        })
        save_task(actor=self.actor, project_id=self.project.pk, data={
            "category": category, "serial_number": "abc", "title": "Cable two"
        })
        response = self.upload(
            ("Cable Works", [("aBc", "Updated cable", "EA", 1, None)]),
        )
        self.assertContains(response, "more than one existing work")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
        self.assertEqual(PulseTask.objects.filter(category=category).count(), 2)

    def test_category_changed_after_preview_rejects_atomic_import(self):
        category = save_category(actor=self.actor, project_id=self.project.pk,
                                 data={"name": "Civil Steel"})
        self.assertEqual(self.upload(
            ("Civil Steel", [("1", "First work", "EA", 3, None)]),
        ).status_code, 302)
        batch = PulseWorkImportBatch.objects.get(project=self.project)
        save_category(actor=self.actor, project_id=self.project.pk,
                      category_id=category.pk, data={"name": "Civil & Steel"})
        response = self.client.post(reverse(
            "project_pulse:works_import_apply", args=[self.project.code, batch.pk]
        ))
        self.assertEqual(response.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.status, PulseWorkImportBatch.Status.PREVIEW)
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 0)
