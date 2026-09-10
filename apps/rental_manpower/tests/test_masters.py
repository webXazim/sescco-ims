from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.rental_manpower.models import ProjectStatus, RentalWorker, SupplierStatus
from apps.rental_manpower.services import (
    create_project,
    create_supplier,
    create_worker,
    import_workers,
    update_supplier,
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

    def test_supplier_cannot_be_deactivated_with_active_workers(self):
        create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
            worker_number="RW-A",
            full_name="Active Worker",
        )
        with self.assertRaises(ValidationError):
            update_supplier(
                actor_membership=self.owner,
                supplier_id=self.supplier.pk,
                code=self.supplier.code,
                name=self.supplier.name,
                status="Inactive",
            )
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.status, SupplierStatus.ACTIVE)

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
