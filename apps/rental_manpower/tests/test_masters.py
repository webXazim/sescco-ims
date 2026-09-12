from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.rental_manpower.models import ProjectStatus, RentalRateType, RentalWorker, RentalWorkerStatus, SupplierStatus, WorkerAssignment
from apps.rental_manpower.selectors.masters import workers_for_company
from apps.rental_manpower.services import (
    create_project,
    assign_worker,
    create_supplier,
    create_worker,
    import_workers,
    update_supplier,
    archive_supplier, restore_supplier_archive, restore_supplier_trash, delete_unused_supplier, change_supplier_lifecycle, change_worker_lifecycle, restore_worker_trash, delete_unused_worker,
)


class RentalMasterServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme Contracting", slug="acme-rental")
        self.user = User.objects.create_user(username="rental-owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.OWNER,
        )
        self.supplier = create_supplier(
            actor_membership=self.owner,
            code="SUP-A",
            name="Supplier A",
        )

    def test_blank_codes_use_company_sequences_and_create_audit_events(self):
        supplier = create_supplier(actor_membership=self.owner, code="", name="Supplier B")
        project = create_project(
            actor_membership=self.owner,
            code="",
            name="Project A",
            start_date=date(2026, 1, 1),
        )
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="",
            full_name="Worker A",
        )
        self.assertEqual(supplier.code, "SUP-0001")
        self.assertEqual(project.code, "PRJ-0001")
        self.assertEqual(worker.worker_number, "RW-00001")
        self.assertTrue(AuditEvent.objects.filter(action="rental.supplier.created", object_id=str(supplier.pk)).exists())
        self.assertTrue(AuditEvent.objects.filter(action="rental.project.created", object_id=str(project.reference)).exists())
        self.assertTrue(AuditEvent.objects.filter(action="rental.worker.created", object_id=str(worker.pk)).exists())

    def test_blank_project_code_skips_existing_shared_inventory_code(self):
        from apps.projects.models import Project

        Project.objects.create(
            company=self.company,
            code="PRJ-0001",
            name="Existing Inventory Project",
            start_date=date(2026, 1, 1),
        )
        project = create_project(
            actor_membership=self.owner,
            code="",
            name="Rental-created Shared Project",
            start_date=date(2026, 1, 1),
        )
        self.assertEqual(project.code, "PRJ-0002")

    def test_rental_officer_can_edit_but_internal_officer_cannot(self):
        rental_user = User.objects.create_user(username="rental-officer")
        rental = CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        project = create_project(
            actor_membership=rental,
            code="PRJ-R",
            name="Rental Project",
            start_date=date(2026, 1, 1),
        )
        self.assertEqual(project.company, self.company)

        internal_user = User.objects.create_user(username="internal-officer")
        internal = CompanyMembership.objects.create(
            company=self.company,
            user=internal_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        with self.assertRaises(PermissionDenied):
            create_supplier(actor_membership=internal, code="SUP-X", name="Blocked Supplier")

    def test_supplier_temporary_stop_is_not_blocked_by_active_workers(self):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-A",
            full_name="Active Worker",
        )
        stopped = change_supplier_lifecycle(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            action="stop_activity",
            reason="Temporary commercial stop",
        )
        self.assertEqual(stopped.status, SupplierStatus.INACTIVE)
        self.assertIsNotNone(stopped.inactive_on)
        self.assertEqual(stopped.inactive_reason, "Temporary commercial stop")
        worker.refresh_from_db()
        self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE)
        resumed = change_supplier_lifecycle(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            action="activate",
            reason="Commercial activity resumed",
        )
        self.assertEqual(resumed.status, SupplierStatus.ACTIVE)

    def test_worker_temporary_stop_keeps_assignment_and_can_resume(self):
        project = create_project(
            actor_membership=self.owner,
            code="PRJ-STOP",
            name="Stop Activity Project",
            start_date=date(2026, 1, 1),
        )
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-STOP",
            full_name="Temporary Stop Worker",
        )
        assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=project.reference,
            trade="Helper",
            rate_type=RentalRateType.HOURLY,
            rate="10.00",
            effective_date=date(2026, 1, 1),
            reason="Initial assignment",
        )
        stopped = change_worker_lifecycle(
            actor_membership=self.owner,
            worker_id=worker.pk,
            action="stop_activity",
            effective_date=date(2026, 1, 10),
            reason="Temporary activity stop",
        )
        self.assertEqual(stopped.status, RentalWorkerStatus.INACTIVE)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.effective_to)
        resumed = change_worker_lifecycle(
            actor_membership=self.owner,
            worker_id=worker.pk,
            action="activate",
            reason="Activity resumed",
        )
        self.assertEqual(resumed.status, RentalWorkerStatus.ACTIVE)
        self.assertTrue(WorkerAssignment.objects.filter(pk=assignment.pk, effective_to__isnull=True).exists())

    def test_supplier_termination_cascades_to_worker_and_is_final(self):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-TERM",
            full_name="Terminated Worker",
        )
        terminated = change_supplier_lifecycle(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            action="terminate",
            effective_date=date(2026, 1, 15),
            reason="Supplier agreement ended",
        )
        self.assertEqual(terminated.status, SupplierStatus.TERMINATED)
        self.assertEqual(terminated.terminated_on, date(2026, 1, 15))
        worker.refresh_from_db()
        self.assertEqual(worker.status, RentalWorkerStatus.TERMINATED)
        self.assertEqual(worker.terminated_on, date(2026, 1, 15))
        with self.assertRaises(ValidationError):
            change_supplier_lifecycle(
                actor_membership=self.owner,
                supplier_id=self.supplier.pk,
                action="activate",
                reason="Should not reopen terminated relationship",
            )

    def test_completed_project_requires_end_date_and_valid_date_range(self):
        with self.assertRaises(ValidationError):
            create_project(
                actor_membership=self.owner,
                code="PRJ-C",
                name="Completed Project",
                start_date=date(2026, 1, 1),
                status=ProjectStatus.COMPLETED,
            )
        with self.assertRaises(ValidationError):
            create_project(
                actor_membership=self.owner,
                code="PRJ-D",
                name="Invalid Dates",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 1, 31),
            )

    def test_worker_supplier_must_belong_to_same_company(self):
        other_company = Company.objects.create(name="Other", slug="other-rental")
        other_user = User.objects.create_user(username="other-owner")
        other_owner = CompanyMembership.objects.create(
            company=other_company,
            user=other_user,
            role=AccessRole.OWNER,
        )
        other_supplier = create_supplier(actor_membership=other_owner, code="SUP-O", name="Other Supplier")
        with self.assertRaises(type(other_supplier).DoesNotExist):
            create_worker(
                actor_membership=self.owner,
                supplier_id=other_supplier.pk,
                worker_number="RW-X",
                full_name="Cross Company Worker",
            )

    def test_worker_supplier_ownership_cannot_be_rewritten(self):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-OWN",
            full_name="Owned Worker",
        )
        second = create_supplier(actor_membership=self.owner, code="SUP-B", name="Supplier B")
        from apps.rental_manpower.services import update_worker
        with self.assertRaises(ValidationError):
            update_worker(
                actor_membership=self.owner,
                worker_id=worker.pk,
                worker_number=worker.worker_number,
                full_name=worker.full_name,
                supplier_id=second.pk,
                status="Active",
            )
        worker.refresh_from_db()
        self.assertEqual(worker.supplier_id, self.supplier.pk)

    def test_bulk_worker_import_is_all_or_nothing_and_audited(self):
        rows = [
            {
                "worker_number": "RW-101",
                "full_name": "Worker One",
                "national_id": "NID-101",
                "supplier_id": str(self.supplier.pk),
                "status": "Active",
            },
            {
                "worker_number": "RW-102",
                "full_name": "Worker Two",
                "national_id": "NID-102",
                "supplier_id": str(self.supplier.pk),
                "status": "Active",
            },
        ]
        self.assertEqual(import_workers(actor_membership=self.owner, rows=rows, dry_run=True), [])
        self.assertEqual(RentalWorker.objects.for_company(self.company).count(), 0)

        created = import_workers(actor_membership=self.owner, rows=rows)
        self.assertEqual(len(created), 2)
        self.assertEqual(RentalWorker.objects.for_company(self.company).count(), 2)
        self.assertEqual(AuditEvent.objects.filter(company=self.company, action="rental.worker.imported").count(), 2)

    def test_bulk_import_duplicate_rejects_entire_transaction(self):
        rows = [
            {
                "worker_number": "RW-201",
                "full_name": "Worker One",
                "national_id": "NID-201",
                "supplier_id": str(self.supplier.pk),
            },
            {
                "worker_number": "RW-201",
                "full_name": "Worker Two",
                "national_id": "NID-202",
                "supplier_id": str(self.supplier.pk),
            },
        ]
        with self.assertRaises(ValidationError):
            import_workers(actor_membership=self.owner, rows=rows)
        self.assertEqual(RentalWorker.objects.for_company(self.company).count(), 0)
    def test_supplier_archive_restore_preserves_status_and_cascades_worker_visibility(self):
        worker=create_worker(actor_membership=self.owner, supplier_id=self.supplier.pk, worker_number="RW-HIST", full_name="History Worker")
        archived=archive_supplier(actor_membership=self.owner, supplier_id=self.supplier.pk, reason="Contract ended")
        self.assertIsNotNone(archived.archived_at); self.assertEqual(archived.status, SupplierStatus.ACTIVE)
        worker.refresh_from_db(); self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE); self.assertIsNone(worker.archived_at)
        self.assertFalse(workers_for_company(company=self.company, archived=False).filter(pk=worker.pk).exists())
        self.assertTrue(workers_for_company(company=self.company, archived=True).filter(pk=worker.pk).exists())
        restored=restore_supplier_archive(actor_membership=self.owner, supplier_id=archived.pk)
        self.assertIsNone(restored.archived_at); self.assertEqual(restored.status, SupplierStatus.ACTIVE)

    def test_supplier_delete_with_worker_history_is_recoverable(self):
        worker=create_worker(actor_membership=self.owner, supplier_id=self.supplier.pk, worker_number="RW-HIST2", full_name="History Worker Two")
        self.assertEqual(delete_unused_supplier(actor_membership=self.owner, supplier_id=self.supplier.pk, confirmation=self.supplier.code, reason="Supplier removed"), str(self.supplier.pk))
        self.supplier.refresh_from_db(); worker.refresh_from_db()
        self.assertIsNotNone(self.supplier.deleted_at); self.assertIsNone(worker.deleted_at)
        self.assertFalse(workers_for_company(company=self.company, deleted=False).filter(pk=worker.pk).exists())
        self.assertTrue(workers_for_company(company=self.company, deleted=True, archived=None).filter(pk=worker.pk).exists())
        restored=restore_supplier_trash(actor_membership=self.owner, supplier_id=self.supplier.pk)
        self.assertIsNone(restored.deleted_at)
        worker.refresh_from_db(); self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE)
        self.assertTrue(workers_for_company(company=self.company, deleted=False).filter(pk=worker.pk).exists())

    def test_worker_lifecycle_archive_restore_delete_unused(self):
        worker=create_worker(actor_membership=self.owner, supplier_id=self.supplier.pk, worker_number="RW-LIFE", full_name="Lifecycle Worker")
        worker=change_worker_lifecycle(actor_membership=self.owner, worker_id=worker.pk, action="archive", reason="No longer supplied")
        self.assertIsNotNone(worker.archived_at); self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE)
        worker=change_worker_lifecycle(actor_membership=self.owner, worker_id=worker.pk, action="restore_archive", reason="Record needed again")
        self.assertIsNone(worker.archived_at); self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE)
        self.assertEqual(delete_unused_worker(actor_membership=self.owner, worker_id=worker.pk, confirmation="RW-LIFE", reason="Duplicate"), str(worker.pk))
        worker.refresh_from_db(); self.assertIsNotNone(worker.deleted_at)
        worker=restore_worker_trash(actor_membership=self.owner, worker_id=worker.pk)
        self.assertIsNone(worker.deleted_at); self.assertEqual(worker.status, RentalWorkerStatus.ACTIVE)

