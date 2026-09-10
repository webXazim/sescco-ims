from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.rental_manpower.models import RentalWorkerStatus, WorkerAssignment
from apps.rental_manpower.selectors import assignment_on_date
from apps.rental_manpower.services import (
    assign_worker,
    cancel_scheduled_assignment,
    change_worker_rate,
    change_worker_trade,
    create_project,
    create_supplier,
    create_worker,
    release_worker,
    transfer_worker,
    update_project,
    update_worker,
)


class RentalAssignmentServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme Contracting", slug="acme-asg")
        self.user = User.objects.create_user(username="assignment-owner")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.OWNER,
        )
        self.supplier = create_supplier(actor_membership=self.owner, code="SUP-A", name="Supplier A")
        self.project_a = create_project(
            actor_membership=self.owner,
            code="PRJ-A",
            name="Project A",
            start_date=date(2026, 1, 1),
        )
        self.project_b = create_project(
            actor_membership=self.owner,
            code="PRJ-B",
            name="Project B",
            start_date=date(2026, 1, 1),
        )
        self.worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-A",
            full_name="Worker A",
        )

    def test_assignment_transfer_trade_and_rate_preserve_segments(self):
        first = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Helper",
            rate_type="Hourly",
            rate="12.50",
            effective_date=date(2026, 1, 1),
        )
        second = transfer_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_b.pk,
            trade="Helper",
            rate_type="Hourly",
            rate="13.00",
            effective_date=date(2026, 2, 1),
            reason="Project transfer",
        )
        third = change_worker_trade(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            trade="Mason",
            effective_date=date(2026, 2, 10),
            reason="Trade upgrade",
        )
        fourth = change_worker_rate(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            rate_type="Daily",
            rate="150",
            effective_date=date(2026, 2, 20),
            reason="Commercial revision",
        )

        for row in (first, second, third):
            row.refresh_from_db()
        self.assertEqual(first.effective_to, date(2026, 1, 31))
        self.assertEqual(second.effective_to, date(2026, 2, 9))
        self.assertEqual(third.effective_to, date(2026, 2, 19))
        self.assertIsNone(fourth.effective_to)
        self.assertEqual(fourth.trade, "Mason")
        self.assertEqual(fourth.rate_type, "daily")
        self.assertEqual(fourth.rate, Decimal("150"))
        self.assertEqual(WorkerAssignment.objects.for_company(self.company).filter(worker=self.worker).count(), 4)

        on_jan = assignment_on_date(company=self.company, worker_id=self.worker.pk, on_date=date(2026, 1, 15))
        on_feb = assignment_on_date(company=self.company, worker_id=self.worker.pk, on_date=date(2026, 2, 15))
        self.assertEqual(on_jan.project_id, self.project_a.pk)
        self.assertEqual(on_feb.project_id, self.project_b.pk)
        self.assertEqual(on_feb.trade, "Mason")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.transferred").exists())
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.trade_changed").exists())
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.rate_changed").exists())

    def test_second_open_assignment_is_rejected(self):
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Helper",
            rate_type="Hourly",
            rate="10",
            effective_date=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            assign_worker(
                actor_membership=self.owner,
                worker_id=self.worker.pk,
                project_id=self.project_b.pk,
                trade="Helper",
                rate_type="Hourly",
                rate="11",
                effective_date=date(2026, 2, 1),
            )

    def test_release_to_available_then_reassign_preserves_history(self):
        assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Driver",
            rate_type="Daily",
            rate="120",
            effective_date=date(2026, 1, 1),
        )
        released = release_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            effective_date=date(2026, 1, 31),
            disposition="Available",
            reason="Project scope complete",
        )
        self.assertEqual(released.pk, assignment.pk)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, RentalWorkerStatus.ACTIVE)
        next_assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_b.pk,
            trade="Driver",
            rate_type="Daily",
            rate="125",
            effective_date=date(2026, 2, 1),
        )
        self.assertIsNone(next_assignment.effective_to)
        self.assertEqual(WorkerAssignment.objects.for_company(self.company).filter(worker=self.worker).count(), 2)
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.released").exists())

    def test_future_release_cannot_immediately_inactivate_worker(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Worker",
            rate_type="Hourly",
            rate="10",
            effective_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            release_worker(
                actor_membership=self.owner,
                worker_id=self.worker.pk,
                effective_date=tomorrow,
                disposition="Inactive",
            )

    def test_worker_cannot_be_made_inactive_with_current_assignment(self):
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Worker",
            rate_type="Hourly",
            rate="10",
            effective_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            update_worker(
                actor_membership=self.owner,
                worker_id=self.worker.pk,
                worker_number=self.worker.worker_number,
                full_name=self.worker.full_name,
                supplier_id=self.supplier.pk,
                status="Inactive",
            )

    def test_project_cannot_complete_with_open_assignment(self):
        assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Worker",
            rate_type="Hourly",
            rate="10",
            effective_date=date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            update_project(
                actor_membership=self.owner,
                project_id=self.project_a.pk,
                code=self.project_a.code,
                name=self.project_a.name,
                start_date=self.project_a.start_date,
                end_date=date(2026, 12, 31),
                status="Completed",
            )



    def test_second_lifecycle_change_is_blocked_while_future_revision_exists(self):
        today = timezone.localdate()
        assign_worker(
            actor_membership=self.owner, worker_id=self.worker.pk, project_id=self.project_a.pk,
            trade="Helper", rate_type="Hourly", rate="10", effective_date=today - timedelta(days=10),
        )
        transfer_worker(
            actor_membership=self.owner, worker_id=self.worker.pk, project_id=self.project_b.pk,
            trade="Helper", rate_type="Hourly", rate="11", effective_date=today + timedelta(days=10),
        )
        with self.assertRaises(ValidationError):
            change_worker_rate(
                actor_membership=self.owner, worker_id=self.worker.pk, rate_type="Hourly", rate="12",
                effective_date=today + timedelta(days=20),
            )

    def test_cancel_future_transfer_reopens_predecessor_and_retains_cancelled_history(self):
        today = timezone.localdate()
        first = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Helper",
            rate_type="Hourly",
            rate="12",
            effective_date=today - timedelta(days=20),
        )
        future = transfer_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_b.pk,
            trade="Helper",
            rate_type="Hourly",
            rate="13",
            effective_date=today + timedelta(days=10),
            reason="Scheduled transfer",
        )
        first.refresh_from_db()
        self.assertEqual(first.effective_to, today + timedelta(days=9))

        cancelled = cancel_scheduled_assignment(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            reason="Client rescheduled mobilization",
        )
        self.assertEqual(cancelled.pk, future.pk)
        cancelled.refresh_from_db()
        first.refresh_from_db()
        self.assertIsNotNone(cancelled.cancelled_at)
        self.assertEqual(cancelled.cancel_reason, "Client rescheduled mobilization")
        self.assertIsNone(first.effective_to)
        resolved = assignment_on_date(
            company=self.company,
            worker_id=self.worker.pk,
            on_date=today + timedelta(days=15),
        )
        self.assertEqual(resolved.pk, first.pk)
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.cancelled").exists())
        self.assertTrue(AuditEvent.objects.filter(company=self.company, action="rental.assignment.predecessor_reopened").exists())

    def test_cancel_initial_future_assignment_returns_worker_to_available_history(self):
        future = assign_worker(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            project_id=self.project_a.pk,
            trade="Driver",
            rate_type="Daily",
            rate="120",
            effective_date=timezone.localdate() + timedelta(days=7),
        )
        cancel_scheduled_assignment(
            actor_membership=self.owner,
            worker_id=self.worker.pk,
            reason="Mobilization cancelled",
        )
        future.refresh_from_db()
        self.assertIsNotNone(future.cancelled_at)
        self.assertIsNone(assignment_on_date(
            company=self.company, worker_id=self.worker.pk, on_date=future.effective_from
        ))

    def test_internal_only_role_cannot_write_assignments(self):
        internal_user = User.objects.create_user(username="internal-asg")
        internal = CompanyMembership.objects.create(
            company=self.company,
            user=internal_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        with self.assertRaises(PermissionDenied):
            assign_worker(
                actor_membership=internal,
                worker_id=self.worker.pk,
                project_id=self.project_a.pk,
                trade="Worker",
                rate_type="Hourly",
                rate="10",
                effective_date=date(2026, 1, 1),
            )

    def test_cross_company_project_is_rejected(self):
        other = Company.objects.create(name="Other", slug="other-asg")
        other_user = User.objects.create_user(username="other-asg-owner")
        other_owner = CompanyMembership.objects.create(company=other, user=other_user, role=AccessRole.OWNER)
        other_project = create_project(
            actor_membership=other_owner,
            code="OTHER",
            name="Other Project",
            start_date=date(2026, 1, 1),
        )
        with self.assertRaises(type(other_project).DoesNotExist):
            assign_worker(
                actor_membership=self.owner,
                worker_id=self.worker.pk,
                project_id=other_project.pk,
                trade="Worker",
                rate_type="Hourly",
                rate="10",
                effective_date=date(2026, 1, 1),
            )
