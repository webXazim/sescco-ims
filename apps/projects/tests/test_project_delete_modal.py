"""Deletion stays on the project screen and preserves its server-side policy."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.tenant import grant_company_access, primary_company
from apps.projects.models import Project


class ProjectDeleteDialogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = primary_company()
        cls.admin = get_user_model().objects.create_superuser(
            username="project-delete-dialog-admin", password="safe-password", email="pd@example.com"
        )
        cls.member = get_user_model().objects.create_user(
            username="project-delete-dialog-member", password="safe-password"
        )
        grant_company_access(cls.admin, company=cls.company)
        grant_company_access(cls.member, company=cls.company)
        cls.project = Project.objects.create(company=cls.company, code="MODAL-01", name="Dialog Test")

    def request_kwargs(self):
        return {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}

    def test_delete_action_is_modal_trigger_not_a_confirmation_page_link(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("projects:detail", args=[self.project.code]))
        self.assertContains(response, 'data-inventory-delete href="' + reverse("projects:delete", args=[self.project.code]) + '"')
        self.assertContains(response, 'data-inventory-delete-dialog')
        self.assertNotContains(response, 'data-delete-name')

    def test_modal_payload_and_validation_without_page_navigation(self):
        self.client.force_login(self.admin)
        url = reverse("projects:delete", args=[self.project.code])
        response = self.client.get(url, **self.request_kwargs())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertTrue(response.json()["delete_allowed"])
        self.assertNotIn("confirmation_token", response.json())
        self.assertEqual(response.json()["retention_days"], 30)

        # Opening the modal must never delete the project.
        self.project.refresh_from_db()
        self.assertIsNone(self.project.deleted_at)

        success = self.client.post(
            url,
            {},
            **self.request_kwargs(),
        )
        self.assertEqual(success.status_code, 200)
        self.assertEqual(success.json()["redirect_url"], reverse("projects:list"))
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.deleted_at)
        self.assertEqual(self.project.deletion_reason, "Deleted after confirmation click.")

    def test_member_cannot_load_or_submit_modal(self):
        self.client.force_login(self.member)
        url = reverse("projects:delete", args=[self.project.code])
        self.assertEqual(self.client.get(url, **self.request_kwargs()).status_code, 403)
        self.assertEqual(self.client.post(url, {}, **self.request_kwargs()).status_code, 403)
