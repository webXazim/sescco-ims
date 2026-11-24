"""Project Pulse template/report Excel upload, preview and safe reimport."""
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.project_pulse.import_services import parse_workbook
from apps.project_pulse.models import (
    PulseProgressUpdate,
    PulseTask,
    PulseWorkCategory,
    PulseWorkImportBatch,
)
from apps.project_pulse.progress_services import record_progress
from apps.project_pulse.work_services import save_category, save_task
from apps.projects.models import Project

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def build_file(*, sections=None, extra_sheet=False, formulas=False):
    sections = sections if sections is not None else [
        ("Power Transformer", [(1, "Transformer installation", "EA", 3, None),
                               (2, "AVC panels", "EA", 4, 35)]),
        ("Cable Installation", [(1, "Cable laying", "LM", 540, "60%")]),
    ]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Works"
    for category, works in sections:
        sheet.append([category])
        sheet.append(["SN", "Description", "Unit", "Quantity", "% Completion"])
        for work in works:
            sheet.append(work)
    if formulas:
        sheet["E3"] = "=25+25"
    if extra_sheet:
        workbook.create_sheet("More")
    output = BytesIO()
    workbook.save(output)
    return SimpleUploadedFile("works.xlsx", output.getvalue(),
                              content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def build_progress_report(*, project_sheet="Import project", progress=0.5):
    workbook = Workbook()

    def add_report(sheet, category, work_prefix):
        sheet.append(["Work Category", "Works", "Completion (%)", "Issues", "Remarks"])
        sheet.merge_cells("A2:C2")
        sheet["A2"] = category
        sheet.append([
            None,
            f"{work_prefix}.1 - Prepare and level base surface",
            progress,
            "Inspection pending",
            "One basin complete",
        ])
        sheet["C3"].number_format = "0%"
        sheet.append([
            None,
            f"{work_prefix}.2 - Pour and cure concrete",
            1,
            None,
            "Complete",
        ])
        sheet["C4"].number_format = "0%"

    other = workbook.active
    other.title = "Other Site"
    add_report(other, "Other Works", "9")
    selected = workbook.create_sheet(project_sheet)
    add_report(selected, "Foundation", "1")
    workbook.create_sheet("Sheet2")
    output = BytesIO()
    workbook.save(output)
    return SimpleUploadedFile(
        "Work Progress report.xlsx",
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=STORAGES)
class ExcelWorkImportTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="U3 Import", slug="u3-import")
        self.user = get_user_model().objects.create_user(username="u3-owner", password="VeryStrongTestPass!2026")
        self.owner = CompanyMembership.objects.create(company=company, user=self.user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=company, code="U3-PRJ", name="Import project")
        self.other_project = Project.objects.create(company=company, code="U3-OTHER", name="Other project")
        self.client.force_login(self.user)

    def upload(self, data=None):
        response = self.client.post(reverse("project_pulse:works_import_upload", args=[self.project.code]),
                                    {"workbook": data if data is not None else build_file()})
        return response

    def latest(self):
        return PulseWorkImportBatch.objects.filter(project=self.project).latest("pk")

    def apply(self, batch, decisions=None):
        return self.client.post(reverse("project_pulse:works_import_apply", args=[self.project.code, batch.pk]),
                                decisions or {})

    def test_blank_becomes_zero_and_works_import_into_one_project(self):
        response = self.upload()
        self.assertEqual(response.status_code, 302)
        batch = self.latest()
        self.assertEqual(batch.preview_data["counts"], {"new": 3, "changed": 0, "unchanged": 0})
        self.assertEqual(batch.preview_data["items"][0]["progress"], 0)
        self.assertTrue(batch.preview_data["items"][0]["blank_percent"])
        preview = self.client.get(reverse("project_pulse:works_import_preview",
                                          args=[self.project.code, batch.pk]))
        self.assertContains(preview, "Blank → 0%")
        self.assertEqual(self.apply(batch).status_code, 302)
        self.assertEqual(PulseWorkCategory.objects.filter(project=self.project).count(), 2)
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 3)
        self.assertEqual(PulseTask.objects.filter(category__project=self.other_project).count(), 0)
        transformer = PulseTask.objects.get(category__project=self.project, category__name="Power Transformer", serial_number="1")
        self.assertEqual((transformer.progress_percent, transformer.status, transformer.unit),
                         (0, PulseTask.Status.NOT_STARTED, "EA"))
        cable = PulseTask.objects.get(category__project=self.project, category__name="Cable Installation", serial_number="1")
        self.assertEqual((cable.progress_percent, cable.status), (60, PulseTask.Status.IN_PROGRESS))
        self.assertEqual(PulseProgressUpdate.objects.filter(task=cable).count(), 1)
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.created_count, batch.preview_data), ("applied", 3, {}))
        self.assertEqual(self.apply(batch).status_code, 302)  # Already applied; never duplicate.
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 3)

    def test_reimport_default_keeps_existing_completion_even_if_cell_blank(self):
        self.upload()
        self.apply(self.latest())
        task = PulseTask.objects.get(category__project=self.project, category__name="Power Transformer", serial_number="2")
        record_progress(actor=self.owner, project_id=self.project.pk, task_id=task.pk,
                        progress_percent=65, status="auto")
        new_file = build_file(sections=[("Power Transformer", [
            (2, "AVC panels updated", "EA", 4, None),
        ])])
        self.upload(new_file)
        batch = self.latest()
        item = batch.preview_data["items"][0]
        self.assertEqual((item["kind"], item["progress"], item["before"]["progress"]), ("changed", 0, 65))
        self.assertEqual(self.apply(batch).status_code, 302)
        task.refresh_from_db()
        self.assertEqual((task.progress_percent, task.title), (65, "AVC panels"))

    def test_explicit_change_to_blank_percent_resets_to_zero_with_history(self):
        self.upload()
        self.apply(self.latest())
        task = PulseTask.objects.get(category__project=self.project, category__name="Power Transformer", serial_number="2")
        new_file = build_file(sections=[("Power Transformer", [
            (2, "AVC panels", "EA", 4, None),
        ])])
        self.upload(new_file)
        batch = self.latest()
        self.assertEqual(batch.preview_data["items"][0]["kind"], "changed")
        self.assertEqual(self.apply(batch, {"decision_0": "all"}).status_code, 302)
        task.refresh_from_db()
        self.assertEqual((task.progress_percent, task.status), (0, PulseTask.Status.NOT_STARTED))
        self.assertEqual(PulseProgressUpdate.objects.filter(task=task).count(), 2)

    def test_details_only_preserves_progress(self):
        self.upload()
        self.apply(self.latest())
        new_file = build_file(sections=[("Power Transformer", [
            (2, "Changed title", "EA", 8, None),
        ])])
        self.upload(new_file)
        batch = self.latest()
        self.assertEqual(self.apply(batch, {"decision_0": "details"}).status_code, 302)
        work = PulseTask.objects.get(category__project=self.project, category__name="Power Transformer", serial_number="2")
        self.assertEqual((work.title, work.progress_percent, str(work.quantity)), ("Changed title", 35, "8.0000"))
        self.assertEqual(PulseProgressUpdate.objects.filter(task=work).count(), 1)

    def test_reupload_same_workbook_is_idempotent(self):
        self.upload()
        self.apply(self.latest())
        self.upload()
        preview = self.latest().preview_data
        self.assertEqual(preview["counts"], {"new": 0, "changed": 0, "unchanged": 3})
        self.apply(self.latest())
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 3)

    def test_validation_rejects_two_sheets_errors_and_duplicate_serials(self):
        response = self.upload(build_file(extra_sheet=True))
        self.assertContains(response, "exactly one worksheet")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
        response = self.upload(build_file(formulas=True))
        self.assertContains(response, "formulas are not accepted")
        response = self.upload(build_file(sections=[("Power Transformer", [
            (1, "Work one", "EA", 3, 0), (1, "Work two", "EA", 4, 0),
        ])]))
        self.assertContains(response, "duplicate SN")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
        response = self.upload(build_file(sections=[("Power Transformer", [
            (1, "Work one", "EA", 3, 120),
        ])]))
        self.assertContains(response, "between 0 and 100")

    def test_stale_preview_rejected_as_atomic_commit(self):
        self.upload(build_file(sections=[("A", [(1, "One", "EA", 1, None),
                                                   (2, "Two", "EA", 1, None)])]))
        batch = self.latest()
        cat = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "A"})
        save_task(actor=self.owner, project_id=self.project.pk,
                  data={"category": cat, "serial_number": "2", "title": "Now exists"})
        self.apply(batch)
        self.assertEqual(PulseTask.objects.filter(category__project=self.project).count(), 1)
        self.assertEqual(self.latest().status, "preview")

    def test_expired_preview_requires_new_upload(self):
        self.upload()
        batch = self.latest()
        batch.preview_expires_at = timezone.now() - timedelta(minutes=1)
        batch.save()
        self.apply(batch)
        self.assertFalse(PulseTask.objects.filter(category__project=self.project).exists())

    def test_project_scope_applies_to_preview_and_confirm(self):
        self.upload()
        batch = self.latest()
        other_preview = reverse("project_pulse:works_import_preview", args=[self.other_project.code, batch.pk])
        other_apply = reverse("project_pulse:works_import_apply", args=[self.other_project.code, batch.pk])
        self.assertEqual(self.client.get(other_preview).status_code, 404)
        self.assertEqual(self.client.post(other_apply).status_code, 404)

    def test_excel_percent_format_is_scaled_once(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Cable Works"])
        sheet.append(["SN", "Description", "Unit", "Quantity", "% Completion"])
        sheet.append([1, "Cable works", "LM", 100, 0.25])
        sheet["E3"].number_format = "0%"
        output = BytesIO()
        workbook.save(output)
        file = SimpleUploadedFile("works.xlsx", output.getvalue())
        parsed = parse_workbook(file)
        self.assertEqual(parsed["categories"][0]["works"][0]["progress"], 25)

    def test_formatted_multi_sheet_report_imports_matching_project_sheet(self):
        response = self.upload(build_progress_report())
        self.assertEqual(response.status_code, 302)
        batch = self.latest()
        preview = batch.preview_data
        self.assertEqual(preview["layout"], "work_progress_report")
        self.assertEqual(preview["worksheet"], self.project.name)
        self.assertEqual(preview["category_count"], 1)
        self.assertEqual(preview["counts"], {"new": 2, "changed": 0, "unchanged": 0})
        first = preview["items"][0]
        self.assertEqual((first["serial"], first["progress"]), ("1.1", 50))
        self.assertIn("Issues:\nInspection pending", first["description"])
        self.assertIn("Remarks:\nOne basin complete", first["description"])
        self.assertFalse(first["unit_provided"])
        self.assertFalse(first["quantity_provided"])

        preview_page = self.client.get(reverse(
            "project_pulse:works_import_preview",
            args=[self.project.code, batch.pk],
        ))
        self.assertContains(preview_page, "Sheet: Import project")
        self.assertContains(preview_page, "Inspection pending")
        self.assertEqual(self.apply(batch).status_code, 302)
        task = PulseTask.objects.get(
            category__project=self.project,
            category__name="Foundation",
            serial_number="1.1",
        )
        self.assertEqual(task.progress_percent, 50)
        self.assertIn("One basin complete", task.description)
        self.assertEqual(task.unit, "")
        self.assertIsNone(task.quantity)
        event = AuditEvent.objects.get(
            action="pulse.work_import.applied",
            object_id=str(batch.pk),
        )
        self.assertEqual(event.after["worksheet"], "Import project")
        self.assertEqual(event.after["layout"], "work_progress_report")

    def test_report_reimport_preserves_unit_and_quantity_not_present_in_report(self):
        initial = build_file(sections=[(
            "Foundation",
            [("1.1", "Prepare and level base surface", "EA", 7, 25)],
        )])
        self.upload(initial)
        self.apply(self.latest())

        self.upload(build_progress_report())
        batch = self.latest()
        item = batch.preview_data["items"][0]
        self.assertEqual(item["kind"], "changed")
        self.assertNotIn("unit", item["changes"])
        self.assertNotIn("quantity", item["changes"])
        self.assertIn("description", item["changes"])
        self.assertEqual(self.apply(batch, {"decision_0": "all"}).status_code, 302)
        task = PulseTask.objects.get(
            category__project=self.project,
            category__name="Foundation",
            serial_number="1.1",
        )
        self.assertEqual(task.unit, "EA")
        self.assertEqual(str(task.quantity), "7.0000")
        self.assertEqual(task.progress_percent, 50)
        self.assertIn("Inspection pending", task.description)

    def test_multi_sheet_report_requires_a_sheet_matching_selected_project(self):
        response = self.upload(build_progress_report(project_sheet="Different Project"))
        self.assertContains(response, "No report worksheet matches project")
        self.assertContains(response, "Available report sheets")
        self.assertFalse(PulseWorkImportBatch.objects.exists())

    def test_unnumbered_legacy_work_requires_manual_matching(self):
        category = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Power Transformer"})
        save_task(actor=self.owner, project_id=self.project.pk, data={
            "category": category, "serial_number": "", "title": "Transformer installation"})
        response = self.upload()
        self.assertContains(response, "Assign its SN manually")
        self.assertFalse(PulseWorkImportBatch.objects.exists())
