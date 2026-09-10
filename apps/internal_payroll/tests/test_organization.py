from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.internal_payroll.models import Branch, EmployeeOrganizationAssignment, EmploymentStatus
from apps.internal_payroll.services import (
    change_employee_organization,
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
