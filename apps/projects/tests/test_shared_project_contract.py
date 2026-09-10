from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.tests.tenant import primary_company
from apps.core.models import Company
from apps.projects.contracts import (
    project_for_company,
    projects_for_company,
    serialize_shared_project,
    validate_project_work_date,
)
from apps.projects.models import Project


class SharedProjectAuthorityTests(TestCase):
    def setUp(self):
        self.company = primary_company()
        self.project = Project.objects.create(
            company=self.company,
            code="SHARED-01",
            name="Shared Project",
            client_name="Client",
            location="Riyadh",
            manager_name="Project Manager",
            start_date=date(2026, 1, 1),
            expected_completion_date=date(2026, 12, 31),
        )

    def test_public_reference_is_stable_when_code_changes(self):
        reference = self.project.reference
        self.project.code = "SHARED-02"
        self.project.save()
        self.project.refresh_from_db()
        self.assertEqual(self.project.reference, reference)
        self.assertEqual(self.project.code, "SHARED-02")

    def test_resolver_accepts_public_reference_but_is_company_scoped(self):
        resolved = project_for_company(company=self.company, identifier=str(self.project.reference))
        self.assertEqual(resolved.pk, self.project.pk)

        other = Company.objects.create(name="Other Company", legal_name="Other Company", slug="other-company")
        with self.assertRaises(Project.DoesNotExist):
            project_for_company(company=other, identifier=str(self.project.reference))

    def test_project_query_supports_manager_and_on_hold_status(self):
        self.project.status = Project.Status.ON_HOLD
        self.project.save()
        rows = projects_for_company(company=self.company, query="Project Manager", status=Project.Status.ON_HOLD)
        self.assertEqual(list(rows), [self.project])
        self.assertFalse(self.project.accepts_stock_activity)
        self.assertFalse(self.project.accepts_rental_assignment)

    def test_work_date_guard_enforces_active_status_and_project_dates(self):
        validate_project_work_date(project=self.project, work_date=date(2026, 6, 1))
        with self.assertRaises(ValidationError):
            validate_project_work_date(project=self.project, work_date=date(2025, 12, 31))
        self.project.end_date = date(2026, 6, 30)
        self.project.save()
        with self.assertRaises(ValidationError):
            validate_project_work_date(project=self.project, work_date=date(2026, 7, 1))

    def test_new_completion_requires_actual_end_date(self):
        self.project.status = Project.Status.COMPLETED
        with self.assertRaises(ValidationError):
            self.project.save()
        self.project.end_date = date(2026, 9, 10)
        self.project.save()
        self.assertEqual(self.project.status, Project.Status.COMPLETED)

    def test_shared_serializer_uses_uuid_reference_as_public_id(self):
        payload = serialize_shared_project(self.project)
        self.assertEqual(payload["id"], str(self.project.reference))
        self.assertEqual(payload["reference"], str(self.project.reference))
        self.assertEqual(payload["manager"], "Project Manager")
        self.assertTrue(payload["acceptsInventory"])
        self.assertTrue(payload["acceptsRentalAssignments"])
