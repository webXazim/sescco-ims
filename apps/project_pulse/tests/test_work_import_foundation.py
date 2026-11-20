"""Upgrade 1/5: optional BOQ fields and safe project-scoped import metadata."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.forms import PulseCategoryForm, PulseTaskForm
from apps.project_pulse.models import PulseTask, PulseWorkCategory, PulseWorkImportBatch
from apps.project_pulse.work_services import save_category, save_task


class PulseWorkImportFoundationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Pulse U1", slug="pulse-u1")
        self.other_company = Company.objects.create(name="Pulse U1 Other", slug="pulse-u1-other")
        self.user = get_user_model().objects.create_user(username="pulse-u1-owner", password="OwnerStrong!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="PULSE-U1", name="Work import staging")
        self.other_project = Project.objects.create(company=self.other_company, code="PULSE-U1-OTHER", name="Separate company")
        self.cat = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Power Transformer"})

    def create_work(self, category=None, **changes):
        data = {
            "category": category or self.cat,
            "title": "Install transformer",
            "serial_number": "1",
            "unit": "EA",
            "quantity": Decimal("4.1250"),
            "status": PulseTask.Status.NOT_STARTED,
        }
        data.update(changes)
        return save_task(actor=self.owner, project_id=self.project.pk, data=data)

    def test_category_form_requires_name_only(self):
        self.assertEqual(list(PulseCategoryForm().fields), ["name"])
        self.client.force_login(self.user)
        response = self.client.post(reverse("project_pulse:category_new", args=[self.project.code]), {"name": "Cable Installation"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PulseWorkCategory.objects.filter(project=self.project, name="Cable Installation").exists())

    def test_category_edit_preserves_legacy_description_order_weight(self):
        self.cat.description = "Legacy text"
        self.cat.sort_order = 12
        self.cat.progress_weight = Decimal("2.00")
        self.cat.save()
        self.client.force_login(self.user)
        response = self.client.post(reverse("project_pulse:category_edit", args=[self.project.code, self.cat.pk]), {"name": "Electrical Equipment"})
        self.assertEqual(response.status_code, 302)
        self.cat.refresh_from_db()
        self.assertEqual((self.cat.description, self.cat.sort_order, self.cat.progress_weight),
                         ("Legacy text", 12, Decimal("2.00")))

    def test_optional_work_details_persist_and_reject_negative_quantity(self):
        row = self.create_work()
        row.refresh_from_db()
        self.assertEqual((row.serial_number, row.unit, row.quantity), ("1", "EA", Decimal("4.1250")))
        self.assertEqual(row.progress_percent, 0)
        self.assertIsNone(row.last_import_batch_id)
        self.assertIsNone(row.import_row_number)
        with self.assertRaises(ValidationError):
            self.create_work(serial_number="2", quantity=Decimal("-0.01"))

    def test_same_sn_different_category_allowed_but_not_same_category(self):
        self.create_work()
        with self.assertRaises(ValidationError):
            self.create_work(title="Duplicate", serial_number="1")
        other = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Cable Installation"})
        row = self.create_work(category=other, title="Cable works")
        self.assertEqual(row.serial_number, "1")

    def test_legacy_works_can_have_blank_sn_and_quantity(self):
        self.create_work(serial_number="", unit="", quantity=None)
        self.create_work(serial_number="", unit="", quantity=None, title="Existing second work")
        self.assertEqual(PulseTask.objects.filter(category=self.cat).count(), 2)

    def test_task_form_shows_optional_work_fields(self):
        form = PulseTaskForm(project=self.project)
        for field in ("serial_number", "unit", "quantity"):
            self.assertIn(field, form.fields)
        self.assertFalse(form.fields["quantity"].required)
        self.assertFalse(form.fields["serial_number"].required)

    def test_batch_company_scope_and_task_provenance(self):
        batch = PulseWorkImportBatch.objects.create(
            project=self.project, uploaded_by=self.owner, filename="works.xlsx",
            sha256="a" * 64,
        )
        row = self.create_work()
        row.last_import_batch = batch
        row.import_row_number = 3
        row.save()
        row.refresh_from_db()
        self.assertEqual((row.last_import_batch_id, row.import_row_number), (batch.pk, 3))
        with self.assertRaises(ValidationError):
            PulseWorkImportBatch.objects.create(
                project=self.other_project, uploaded_by=self.owner,
                filename="invalid.xlsx", sha256="b" * 64,
            )
