from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.core.services.lifecycle import (
    archive_reason_required,
    can_archive,
    can_deactivate,
    can_delete,
    can_restore,
    lifecycle_capabilities,
)
from apps.internal_payroll.models import Branch, BranchKind, Department, EmployeeOrganizationAssignment, EmploymentStatus, InternalEmployee
from apps.internal_payroll.selectors.organization import employees_for_company
from apps.internal_payroll.services import (
    change_employee_organization,
    change_employee_lifecycle,
    archive_employee, archive_branch, archive_department,
    restore_employee_archive, restore_branch_archive, restore_department_archive,
    restore_employee_trash, restore_branch_trash, restore_department_trash,
    delete_unused_employee, delete_unused_branch, delete_unused_department,
    create_branch,
    create_department,
    create_employee,
    update_branch,
)


class InternalOrganizationServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", legal_name="Acme LLC", slug="acme")
        self.owner_user = User.objects.create_user(username="owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner_user,
            role=AccessRole.OWNER,
            is_active=True,
        )
        self.branch = create_branch(actor_membership=self.owner, code="HQ", name="Head Office", location="Riyadh")
        self.department = create_department(actor_membership=self.owner, code="FIN", name="Finance")

    def create_employee(self):
        return create_employee(
            actor_membership=self.owner,
            employee_number="0001",
            full_name="Test Employee",
            joining_date=date(2020, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Accountant",
            national_id="1234567890",
            phone="0500000000",
        )

    def test_create_employee_creates_one_open_assignment_and_audit(self):
        employee = self.create_employee()
        assignments = EmployeeOrganizationAssignment.objects.filter(employee=employee)
        self.assertEqual(assignments.count(), 1)
        self.assertIsNone(assignments.get().effective_to)
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                action="internal.employee.created",
                object_id=str(employee.pk),
            ).exists()
        )

    def test_internal_officer_can_edit_but_reviewer_cannot(self):
        officer_user = User.objects.create_user(username="officer")
        officer = CompanyMembership.objects.create(
            company=self.company,
            user=officer_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        branch = create_branch(actor_membership=officer, code="BR2", name="Second Office")
        self.assertEqual(branch.company, self.company)

        reviewer_user = User.objects.create_user(username="reviewer")
        reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        with self.assertRaises(PermissionDenied):
            create_department(actor_membership=reviewer, code="OPS", name="Operations")

    def test_branch_cannot_be_inactivated_while_current_employee_is_employed(self):
        self.create_employee()
        with self.assertRaises(ValidationError):
            update_branch(
                actor_membership=self.owner,
                branch_id=self.branch.pk,
                code=self.branch.code,
                name=self.branch.name,
                location=self.branch.location,
                address=self.branch.address,
                manager_name=self.branch.manager_name,
                is_active=False,
            )

    def test_organization_change_closes_previous_assignment_and_preserves_history(self):
        employee = self.create_employee()
        next_branch = create_branch(actor_membership=self.owner, code="DAM", name="Dammam Office")
        next_department = create_department(actor_membership=self.owner, code="ADM", name="Administration")
        effective = date.today()
        if effective <= employee.joining_date:
            effective = employee.joining_date + timedelta(days=1)

        change_employee_organization(
            actor_membership=self.owner,
            employee_id=employee.pk,
            branch_id=next_branch.pk,
            department_id=next_department.pk,
            position="Senior Accountant",
            effective_from=effective,
            reason="Office transfer",
        )
        rows = list(EmployeeOrganizationAssignment.objects.filter(employee=employee).order_by("effective_from"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].effective_to, effective - timedelta(days=1))
        self.assertEqual(rows[1].branch, next_branch)
        self.assertIsNone(rows[1].effective_to)
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                action="internal.employee.organization_changed",
                object_id=str(employee.pk),
            ).exists()
        )

    def test_cross_company_master_cannot_be_assigned(self):
        other_company = Company.objects.create(name="Other", slug="other")
        other_user = User.objects.create_user(username="other-owner")
        other_owner = CompanyMembership.objects.create(
            company=other_company,
            user=other_user,
            role=AccessRole.OWNER,
        )
        other_branch = create_branch(actor_membership=other_owner, code="HQ", name="Other HQ")
        with self.assertRaises(Branch.DoesNotExist):
            create_employee(
                actor_membership=self.owner,
                employee_number="0002",
                full_name="Cross Tenant",
                joining_date=date(2020, 1, 1),
                branch_id=other_branch.pk,
                department_id=self.department.pk,
                position="Clerk",
            )


    def test_blank_master_codes_use_company_number_sequences(self):
        branch = create_branch(actor_membership=self.owner, code="", name="Auto Branch")
        department = create_department(actor_membership=self.owner, code="", name="Auto Department")
        employee = create_employee(
            actor_membership=self.owner,
            employee_number="",
            full_name="Auto Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Coordinator",
        )
        self.assertEqual(branch.code, "BR-0001")
        self.assertEqual(department.code, "DEP-0001")
        self.assertEqual(employee.employee_number, "0001")

    def test_terminated_employee_requires_end_date(self):
        with self.assertRaises(ValidationError):
            create_employee(
                actor_membership=self.owner,
                employee_number="0009",
                full_name="Terminated Employee",
                joining_date=date(2020, 1, 1),
                branch_id=self.branch.pk,
                department_id=self.department.pk,
                position="Coordinator",
                status="Terminated",
            )

    def test_employee_status_value_is_persisted_as_domain_choice(self):
        employee = create_employee(
            actor_membership=self.owner,
            employee_number="0003",
            full_name="Leave Employee",
            joining_date=date(2020, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Coordinator",
            status="On Leave",
        )
        self.assertEqual(employee.status, EmploymentStatus.ON_LEAVE)


    def test_stop_activity_alias_sets_employee_inactive(self):
        employee = self.create_employee()
        employee = change_employee_lifecycle(
            actor_membership=self.owner, employee_id=employee.pk, action="stop_activity",
            reason="Temporary operational stop",
        )
        self.assertEqual(employee.status, EmploymentStatus.INACTIVE)
        self.assertIsNone(employee.employment_end_date)

    def test_terminate_employee_sets_end_date_and_closes_current_assignment(self):
        employee = self.create_employee()
        end_date = date.today()
        employee = change_employee_lifecycle(
            actor_membership=self.owner, employee_id=employee.pk, action="terminate",
            effective_date=end_date, reason="Employment ended",
        )
        self.assertEqual(employee.status, EmploymentStatus.TERMINATED)
        self.assertEqual(employee.employment_end_date, end_date)
        assignment = EmployeeOrganizationAssignment.objects.get(employee=employee)
        self.assertEqual(assignment.effective_to, end_date)

    def test_active_employee_can_be_archived_and_restored_without_status_rewrite(self):
        employee = self.create_employee()
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)
        employee = archive_employee(actor_membership=self.owner, employee_id=employee.pk, reason="File closed")
        self.assertIsNotNone(employee.archived_at)
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)
        employee = restore_employee_archive(actor_membership=self.owner, employee_id=employee.pk, reason="Needed for review")
        self.assertIsNone(employee.archived_at)
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)

    def test_branch_and_department_archive_cascade_without_rewriting_assignment_history(self):
        employee = self.create_employee()
        branch = archive_branch(actor_membership=self.owner, branch_id=self.branch.pk, reason="Office closed")
        department = archive_department(actor_membership=self.owner, department_id=self.department.pk, reason="Reorganization")
        self.assertIsNotNone(branch.archived_at); self.assertTrue(branch.is_active)
        self.assertIsNotNone(department.archived_at); self.assertTrue(department.is_active)
        self.assertEqual(EmployeeOrganizationAssignment.objects.filter(employee=employee).count(), 1)
        employee.refresh_from_db()
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)
        self.assertFalse(employees_for_company(company=self.company, archived=False).filter(pk=employee.pk).exists())
        self.assertTrue(employees_for_company(company=self.company, archived=True).filter(pk=employee.pk).exists())
        branch = restore_branch_archive(actor_membership=self.owner, branch_id=branch.pk)
        department = restore_department_archive(actor_membership=self.owner, department_id=department.pk)
        self.assertIsNone(branch.archived_at); self.assertTrue(branch.is_active)
        self.assertIsNone(department.archived_at); self.assertTrue(department.is_active)

    def test_branch_delete_soft_deletes_current_employees_and_restores_exact_cascade(self):
        employee = self.create_employee()
        self.assertEqual(
            delete_unused_branch(
                actor_membership=self.owner, branch_id=self.branch.pk,
                confirmation=self.branch.code, reason="Office removed",
            ),
            str(self.branch.pk),
        )
        self.branch.refresh_from_db(); employee.refresh_from_db()
        self.assertIsNotNone(self.branch.deleted_at)
        self.assertIsNotNone(employee.deleted_at)
        self.assertEqual(employee.deleted_at, self.branch.deleted_at)
        self.assertEqual(employee.purge_after, self.branch.purge_after)
        self.assertEqual(EmployeeOrganizationAssignment.objects.filter(employee=employee).count(), 1)
        self.assertFalse(employees_for_company(company=self.company, deleted=False).filter(pk=employee.pk).exists())
        self.assertTrue(employees_for_company(company=self.company, deleted=True, archived=None).filter(pk=employee.pk).exists())

        restore_branch_trash(actor_membership=self.owner, branch_id=self.branch.pk)
        self.branch.refresh_from_db(); employee.refresh_from_db()
        self.assertIsNone(self.branch.deleted_at)
        self.assertIsNone(employee.deleted_at)
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)
        self.assertTrue(employees_for_company(company=self.company, deleted=False).filter(pk=employee.pk).exists())

    def test_department_delete_soft_deletes_current_employees_and_restores_exact_cascade(self):
        employee = self.create_employee()
        self.assertEqual(
            delete_unused_department(
                actor_membership=self.owner, department_id=self.department.pk,
                confirmation=self.department.code, reason="Department removed",
            ),
            str(self.department.pk),
        )
        self.department.refresh_from_db(); employee.refresh_from_db()
        self.assertIsNotNone(self.department.deleted_at)
        self.assertIsNotNone(employee.deleted_at)
        self.assertEqual(employee.deleted_at, self.department.deleted_at)
        self.assertEqual(employee.purge_after, self.department.purge_after)
        self.assertEqual(EmployeeOrganizationAssignment.objects.filter(employee=employee).count(), 1)

        restore_department_trash(actor_membership=self.owner, department_id=self.department.pk)
        self.department.refresh_from_db(); employee.refresh_from_db()
        self.assertIsNone(self.department.deleted_at)
        self.assertIsNone(employee.deleted_at)
        self.assertEqual(employee.status, EmploymentStatus.ACTIVE)
        self.assertTrue(employees_for_company(company=self.company, deleted=False).filter(pk=employee.pk).exists())

    def test_parent_restore_does_not_resurrect_independently_deleted_employee(self):
        employee = self.create_employee()
        delete_unused_employee(
            actor_membership=self.owner, employee_id=employee.pk,
            confirmation=employee.employee_number, reason="Duplicate employee master",
        )
        employee.refresh_from_db()
        employee_purge_after = employee.purge_after

        delete_unused_branch(
            actor_membership=self.owner, branch_id=self.branch.pk,
            confirmation=self.branch.code, reason="Office removed",
        )
        restore_branch_trash(actor_membership=self.owner, branch_id=self.branch.pk)

        employee.refresh_from_db()
        self.assertIsNotNone(employee.deleted_at)
        self.assertEqual(employee.purge_after, employee_purge_after)

    def test_parent_restore_never_resurrects_child_redeleted_after_independent_restore(self):
        employee = self.create_employee()
        delete_unused_branch(
            actor_membership=self.owner, branch_id=self.branch.pk,
            confirmation=self.branch.code, reason="Office removed",
        )
        self.branch.refresh_from_db(); employee.refresh_from_db()
        original_parent_deleted_at = self.branch.deleted_at

        # The child is deliberately recovered on its own, which releases the
        # original parent-cascade ownership, then deleted again as a separate
        # lifecycle event while the parent remains in Trash.
        restore_employee_trash(actor_membership=self.owner, employee_id=employee.pk)
        employee.refresh_from_db()
        self.assertIsNone(employee.deleted_at)
        delete_unused_employee(
            actor_membership=self.owner, employee_id=employee.pk,
            confirmation=employee.employee_number, reason="Separate duplicate cleanup",
        )
        employee.refresh_from_db()
        if employee.deleted_at == original_parent_deleted_at:
            # Make the independent window unambiguously distinct even on a DB
            # backend with coarse timestamp precision.
            independent_deleted_at = original_parent_deleted_at + timedelta(seconds=1)
            employee.deleted_at = independent_deleted_at
            employee.purge_after = independent_deleted_at + timedelta(days=30)
            employee.save(update_fields=("deleted_at", "purge_after", "updated_at"))

        restore_branch_trash(actor_membership=self.owner, branch_id=self.branch.pk)
        self.branch.refresh_from_db(); employee.refresh_from_db()
        self.assertIsNone(self.branch.deleted_at)
        self.assertIsNotNone(employee.deleted_at)
        self.assertEqual(employee.deletion_reason, "Separate duplicate cleanup")

    def test_reactivate_employee_requires_current_active_organization_masters(self):
        employee = self.create_employee()
        employee = change_employee_lifecycle(actor_membership=self.owner, employee_id=employee.pk, action="deactivate", reason="Stopped")
        archive_branch(actor_membership=self.owner, branch_id=self.branch.pk, reason="Office retired")
        with self.assertRaises(ValidationError):
            change_employee_lifecycle(actor_membership=self.owner, employee_id=employee.pk, action="activate", reason="Return")

    def test_employee_uses_central_lifecycle_authority_and_audit_metadata(self):
        employee = self.create_employee()
        self.assertTrue(can_deactivate(employee))
        self.assertTrue(can_archive(employee))
        self.assertFalse(can_restore(employee))
        self.assertTrue(can_delete(employee))
        self.assertTrue(archive_reason_required(employee))

        employee = change_employee_lifecycle(
            actor_membership=self.owner, employee_id=employee.pk, action="deactivate", reason="Seasonal stop",
        )
        self.assertTrue(can_archive(employee))
        employee = archive_employee(
            actor_membership=self.owner, employee_id=employee.pk, reason="Historical record",
        )
        self.assertTrue(can_restore(employee))
        capabilities = lifecycle_capabilities(employee)
        self.assertEqual(capabilities["policy"], "InternalEmployeeLifecyclePolicy")
        event = AuditEvent.objects.filter(
            company=self.company, action="internal.employee.archived", object_id=str(employee.pk)
        ).latest("created_at")
        self.assertEqual(event.metadata["lifecycle_action"], "archive")
        self.assertEqual(event.metadata["lifecycle_policy"], "InternalEmployeeLifecyclePolicy")
        self.assertEqual(event.metadata["reason"], "Historical record")
        self.assertIn("dependency_counts", event.metadata)

    def test_unused_employee_can_be_deleted_but_confirmation_is_required(self):
        employee = self.create_employee()
        employee_id = employee.pk
        with self.assertRaises(ValidationError):
            delete_unused_employee(actor_membership=self.owner, employee_id=employee_id, confirmation="WRONG")
        deleted = delete_unused_employee(
            actor_membership=self.owner, employee_id=employee_id, confirmation=employee.employee_number, reason="Duplicate onboarding",
        )
        self.assertEqual(deleted, str(employee_id))
        employee.refresh_from_db()
        self.assertIsNotNone(employee.deleted_at)
        self.assertIsNotNone(employee.purge_after)
        restored = restore_employee_trash(actor_membership=self.owner, employee_id=employee_id)
        self.assertIsNone(restored.deleted_at)
        self.assertEqual(restored.status, EmploymentStatus.ACTIVE)
