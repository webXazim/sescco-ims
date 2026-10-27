"""Name-only project creation must preserve historical Inventory/Payroll IDs."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Company
from apps.core.tests.tenant import grant_company_access, primary_company
from apps.projects.forms import ProjectForm
from apps.projects.models import Project


class ProjectNameTagTests(TestCase):
    def setUp(self):
        self.company = primary_company()
        self.user = get_user_model().objects.create_superuser(
            username="project-name-tag-admin", email="project-tag@example.invalid", password="safe-password"
        )
        grant_company_access(self.user, company=self.company)
        self.client.force_login(self.user)

    def create_project(self, name, **extra):
        return self.client.post(reverse("projects:create"), {"name": name, **extra})

    def test_create_page_asks_only_for_name_and_not_code(self):
        response = self.client.get(reverse("projects:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="name"')
        self.assertNotContains(response, 'name="code"')
        self.assertContains(response, "no separate code is required")

    def test_post_without_code_generates_stable_internal_code(self):
        response = self.create_project("  Wadi Safar   Hotel  ", code="UNTRUSTED")
        self.assertRedirects(response, reverse("projects:list"))
        project = Project.objects.get(name="Wadi Safar Hotel")
        self.assertEqual(project.code, "WADI-SAFAR-HOTEL")
        self.assertNotEqual(project.code, "UNTRUSTED")
        self.assertContains(self.client.get(reverse("projects:list")), "Wadi Safar Hotel")
        self.assertEqual(self.client.get(reverse("projects:detail", args=[project.code])).status_code, 200)

    def test_colliding_codes_get_company_scoped_suffixes(self):
        self.create_project("Road Works")
        self.create_project("Road-Works")
        codes = set(Project.objects.for_company(self.company).filter(name__in=["Road Works", "Road-Works"]).values_list("code", flat=True))
        self.assertEqual(codes, {"ROAD-WORKS", "ROAD-WORKS-2"})

    def test_name_change_preserves_links_and_public_reference(self):
        self.create_project("Old Project")
        project = Project.objects.get(code="OLD-PROJECT")
        reference = project.reference
        edit_url = reverse("projects:edit", args=[project.code])
        edit_page = self.client.get(edit_url)
        self.assertNotContains(edit_page, 'name="code"')
        response = self.client.post(edit_url, {"name": "Renamed Project", "code": "CHANGED"})
        self.assertRedirects(response, reverse("projects:detail", args=[project.code]))
        project.refresh_from_db()
        self.assertEqual(project.reference, reference)
        self.assertEqual(project.code, "OLD-PROJECT")
        self.assertEqual(project.name, "Renamed Project")
        self.assertEqual(str(project), "Renamed Project")

    def test_arabic_name_works_without_a_code_field(self):
        response = self.create_project("مشروع الرياض")
        self.assertRedirects(response, reverse("projects:list"))
        project = Project.objects.get(name="مشروع الرياض")
        self.assertEqual(project.code, "PROJECT")
        self.create_project("مشروع الدمام")
        self.assertEqual(Project.objects.get(name="مشروع الدمام").code, "PROJECT-2")

    def test_internal_code_is_limited_to_database_column_width(self):
        self.create_project("An Extremely Long Project Name That Cannot Fit In The Code")
        project = Project.objects.get(name="An Extremely Long Project Name That Cannot Fit In The Code")
        self.assertLessEqual(len(project.code), 30)
