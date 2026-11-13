"""U06 approval, private attachment and payment boundary regression tests."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import _clean_permissions
from apps.accounts.models import CompanyMembership, AccessProfile, AccessProfilePermission
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.project_pulse.work_services import save_category, save_task
from apps.project_pulse.expense_services import (
    save_expense_category, save_expense, submit_expense, review_expense,
    expense_rollups, record_expense_payment, void_expense_payment,
    void_expense, upload_expense_attachment,
)
from apps.project_pulse.models import PulseExpenseChange, PulseExpensePayment, PulseExpenseAttachment

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ExpenseWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="U06 company", slug="u06-company")
        self.owner_user = get_user_model().objects.create_user(username="u06-owner", password="VerySafePassword1!")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="U06-ONE", name="U06 One")
        self.second = Project.objects.create(company=self.company, code="U06-TWO", name="U06 Two")
        self.category = save_category(actor=self.owner, project_id=self.project.pk, data={"name": "Civil"})
        self.task = save_task(actor=self.owner, project_id=self.project.pk,
                              data={"category": self.category, "title": "Excavation", "status": "in_progress"})
        self.expense_category = save_expense_category(actor=self.owner, project_id=self.project.pk,
                                                      data={"name": "Equipment"})
        self.expense = save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, data={
            "expense_category": self.expense_category, "description": "Excavator rental",
            "amount": Decimal("300.00"), "expense_date": date(2026, 11, 13)})

    def submit(self):
        return submit_expense(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk)

    def approve(self):
        self.submit()
        return review_expense(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk, approve=True)

    def payment(self, amount="100.00"):
        return record_expense_payment(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk,
            data={"amount": Decimal(amount), "paid_on": date(2026, 11, 13), "method": "bank", "reference": "XYZ"})

    def test_new_draft_not_cost_and_review_controls_totals(self):
        self.assertEqual(self.expense.approval_status, "draft")
        self.assertEqual(expense_rollups(self.project)["approved_total"], Decimal("0.00"))
        self.assertEqual(expense_rollups(self.project)["total"], Decimal("300.00"))
        with self.assertRaises(ValidationError):
            self.payment()
        self.submit()
        self.assertEqual(expense_rollups(self.project)["pending_total"], Decimal("300.00"))
        with self.assertRaises(ValidationError):
            save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, expense_id=self.expense.pk,
                data={"expense_category": self.expense_category, "description": "Changed"})
        self.assertEqual(expense_rollups(self.project)["approved_total"], Decimal("0.00"))
        review_expense(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk, approve=True)
        self.assertEqual(expense_rollups(self.project)["approved_total"], Decimal("300.00"))
        self.assertEqual(PulseExpenseChange.objects.filter(entry=self.expense, action="approved").count(), 1)
        with self.assertRaises(ValidationError):
            review_expense(actor=self.owner, project_id=self.project.pk,
                task_id=self.task.pk, expense_id=self.expense.pk, approve=True)

    def test_rejection_requires_reason_then_revise_and_resubmit(self):
        self.submit()
        with self.assertRaises(ValidationError):
            review_expense(actor=self.owner, project_id=self.project.pk,
                task_id=self.task.pk, expense_id=self.expense.pk, approve=False)
        review_expense(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk, approve=False, note="Wrong rate")
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.approval_status, "rejected")
        save_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk, expense_id=self.expense.pk,
            data={"expense_category": self.expense_category, "description": "Revised rate", "amount": Decimal("290.00")})
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.approval_status, "draft")
        self.assertEqual(self.expense.review_note, "")
        self.submit()
        self.assertEqual(expense_rollups(self.project)["pending_total"], Decimal("290.00"))

    def test_payment_partial_exact_and_reversal(self):
        self.approve()
        a = self.payment("100.00")
        b = self.payment("200.00")
        self.assertEqual(expense_rollups(self.project)["paid_total"], Decimal("300.00"))
        with self.assertRaises(ValidationError):
            self.payment("0.01")
        with self.assertRaises(ValidationError):
            void_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
                         expense_id=self.expense.pk, reason="Correction")
        void_expense_payment(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk, payment_id=a.pk, reason="Bank reversal")
        self.assertEqual(expense_rollups(self.project)["paid_total"], Decimal("200.00"))
        with self.assertRaises(ValidationError):
            void_expense_payment(actor=self.owner, project_id=self.project.pk,
                task_id=self.task.pk, expense_id=self.expense.pk, payment_id=a.pk, reason="Again")
        self.payment("100.00")
        self.assertEqual(PulseExpensePayment.objects.filter(entry=self.expense).count(), 3)
        with self.assertRaises(ValidationError):
            b.delete()

    def test_access_profiles_and_http_restrictions(self):
        for code in ("pulse.expenses.approve", "pulse.expense_payments.manage", "pulse.expense_attachments.manage"):
            self.assertIn(code, [choice.value for choice in AccessPermission])
        with self.assertRaises(ValidationError):
            _clean_permissions(["pulse.expenses.approve"])
        user = get_user_model().objects.create_user(username="u06-readonly", password="VerySafePassword1!")
        profile = AccessProfile.objects.create(company=self.company, key="custom-u06-readonly", name="Read only")
        for permission in ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view"):
            AccessProfilePermission.objects.create(profile=profile, permission=permission)
        CompanyMembership.objects.create(company=self.company, user=user,
            role=AccessRole.CUSTOM, access_profile=profile)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:expense_detail", args=[self.project.code, self.task.pk, self.expense.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_pulse:expense_approvals", args=[self.project.code])).status_code, 403)
        self.assertEqual(self.client.post(reverse("project_pulse:expense_submit", args=[self.project.code, self.task.pk, self.expense.pk])).status_code, 403)
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("project_pulse:expense_detail", args=[self.second.code, self.task.pk, self.expense.pk])).status_code, 404)

    def test_non_owner_cannot_self_approve(self):
        user = get_user_model().objects.create_user(username="u06-reviewer", password="VerySafePassword1!")
        profile = AccessProfile.objects.create(company=self.company, key="custom-u06-reviewer", name="Reviewer")
        for code in ("pulse.overview.view", "pulse.projects.view", "pulse.tasks.view", "pulse.expenses.view", "pulse.expenses.manage", "pulse.expenses.approve"):
            AccessProfilePermission.objects.create(profile=profile, permission=code)
        member = CompanyMembership.objects.create(company=self.company, user=user,
                                                  role=AccessRole.CUSTOM, access_profile=profile)
        own_expense = save_expense(actor=member, project_id=self.project.pk, task_id=self.task.pk,
            data={"expense_category": self.expense_category, "description": "Own cost",
                  "amount": Decimal("10.00"), "expense_date": date(2026, 11, 13)})
        submit_expense(actor=member, project_id=self.project.pk, task_id=self.task.pk, expense_id=own_expense.pk)
        with self.assertRaises(PermissionDenied):
            review_expense(actor=member, project_id=self.project.pk, task_id=self.task.pk,
                           expense_id=own_expense.pk, approve=True)
        review_expense(actor=self.owner, project_id=self.project.pk, task_id=self.task.pk,
                       expense_id=own_expense.pk, approve=True)

    def test_private_evidence_validation_and_project_isolation(self):
        bad = SimpleUploadedFile("receipt.pdf", b"<script>alert(1)</script>", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            upload_expense_attachment(actor=self.owner, project_id=self.project.pk,
                task_id=self.task.pk, expense_id=self.expense.pk, upload=bad)
        good = SimpleUploadedFile("receipt.pdf", b"%PDF-1.4\n1 0 obj\nendobj\n", content_type="application/pdf")
        attachment = upload_expense_attachment(actor=self.owner, project_id=self.project.pk,
            task_id=self.task.pk, expense_id=self.expense.pk, upload=good)
        self.assertTrue(PulseExpenseAttachment.objects.filter(pk=attachment.pk).exists())
        try:
            self.client.force_login(self.owner_user)
            url = reverse("project_pulse:expense_attachment_download", args=[self.project.code, self.task.pk, self.expense.pk, attachment.pk])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            # Middleware may replace streaming_content and leave
            # FileResponse.file_to_stream as None. Avoid touching that private
            # implementation detail or calling response.close() here: Django's
            # request_finished signal can close TestCase's transaction connection.
            # The response is released by normal test cleanup.
            self.assertTrue(response.streaming)
            scoped_url = reverse("project_pulse:expense_attachment_download", args=[self.second.code, self.task.pk, self.expense.pk, attachment.pk])
            self.assertEqual(self.client.get(scoped_url).status_code, 404)
        finally:
            attachment.file.storage.delete(attachment.file.name)
