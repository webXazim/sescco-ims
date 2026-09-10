from datetime import timedelta

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project
from apps.rental_manpower.models import WorkerAssignment
from apps.rental_manpower.selectors.assignments import serialize_assignment
from apps.rental_manpower.services import assign_worker, create_project, create_supplier, create_worker, release_worker


class RentalSharedProjectMergeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Merged Contracting", slug="merged-rental-project")
        self.user = User.objects.create_user(username="merged-rental-owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company, user=self.user, role=AccessRole.OWNER
        )
        self.supplier = create_supplier(
            actor_membership=self.owner, code="MP-01", name="Manpower Supplier"
        )
        self.worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-MERGE",
            full_name="Merged Worker",
        )
        today = timezone.localdate()
        self.project = create_project(
            actor_membership=self.owner,
            code="MERGED-PRJ",
            name="Canonical Shared Project",
            start_date=today - timedelta(days=30),
        )

    def test_no_duplicate_rental_project_model_exists(self):
        self.assertIsNone(django_apps.all_models.get("rental_manpower", {}).get("rentalproject"))
        project_field = WorkerAssignment._meta.get_field("project")
        self.assertIs(project_field.remote_field.model, Project)

    def test_rental_serialization_exposes_shared_project_reference(self):
        assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project.reference,
            trade="Helper",
            rate_type="Hourly",
            rate="12.50",
            effective_date=timezone.localdate() - timedelta(days=5),
        )
        payload = serialize_assignment(assignment)
        self.assertEqual(payload["projectId"], str(self.project.reference))
        self.assertNotEqual(payload["projectId"], str(self.project.pk))

    def test_project_cannot_complete_while_rental_assignment_remains_open(self):
        today = timezone.localdate()
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project.reference,
            trade="Helper",
            rate_type="Hourly",
            rate="12.50",
            effective_date=today - timedelta(days=5),
        )
        self.project.status = Project.Status.COMPLETED
        self.project.end_date = today
        with self.assertRaises(ValidationError):
            self.project.save()

        release_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            effective_date=today,
            disposition="available",
            reason="Project complete",
        )
        self.project.save()
        self.assertEqual(self.project.status, Project.Status.COMPLETED)
