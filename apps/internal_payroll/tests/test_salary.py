from datetime import date
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.internal_payroll.models import SalaryStructure, SalaryStructureLine
from apps.internal_payroll.services import (
    archive_overtime_policy,
    archive_salary_component,
    assign_employee_salary_structure,
    create_branch,
    create_department,
    create_employee,
    create_overtime_policy,
    create_salary_component,
    delete_unused_overtime_policy,
    delete_unused_salary_component,
    restore_overtime_policy_archive,
    restore_salary_component_archive,
    update_overtime_policy,
    update_salary_component,
)


class SalarySetupServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="salary-acme")
        self.user = User.objects.create_user(username="salary-owner", password="test-password")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.OWNER,
        )
        branch = create_branch(actor_membership=self.owner, code="HQ", name="Head Office")
        department = create_department(actor_membership=self.owner, code="OPS", name="Operations")
        self.employee = create_employee(
            actor_membership=self.owner,
            employee_number="0001",
            full_name="Salary Employee",
            joining_date=date(2020, 1, 1),
            branch_id=branch.pk,
            department_id=department.pk,
            position="Supervisor",
        )
        self.basic = create_salary_component(
            actor_membership=self.owner,
            code="BASIC",
            name="Basic Salary",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        self.housing = create_salary_component(
            actor_membership=self.owner,
            code="HOUSE",
            name="Housing Allowance",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Housing Allowance",
        )
        self.deduction = create_salary_component(
            actor_membership=self.owner,
            code="DED",
            name="Recurring Deduction",
            category="Deduction",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Deductions",
        )
        self.policy = create_overtime_policy(
            actor_membership=self.owner,
            code="OT15",
            name="Standard OT",
            base_component_id=self.basic.pk,
            divisor="240",
            multiplier="1.5",
        )

    def _assign(self, effective_from=date(2025, 1, 1), basic="4000", housing="1000", deduction="250"):
        return assign_employee_salary_structure(
            actor_membership=self.owner,
            employee_id=self.employee.pk,
            effective_from=effective_from,
            overtime_policy_id=self.policy.pk,
            components=[
                {"component_id": self.basic.pk, "amount": basic},
                {"component_id": self.housing.pk, "amount": housing},
                {"component_id": self.deduction.pk, "amount": deduction},
            ],
        )

    def test_salary_structure_snapshots_component_and_overtime_semantics(self):
        structure = self._assign()
        line = SalaryStructureLine.objects.get(structure=structure, component=self.basic)
        self.assertEqual(line.component_name, "Basic Salary")
        self.assertEqual(line.amount, Decimal("4000.00"))
        self.assertEqual(structure.overtime_policy_name, "Standard OT")
        self.assertEqual(structure.overtime_divisor, Decimal("240.0000"))
        self.assertEqual(structure.overtime_multiplier, Decimal("1.5000"))

        update_salary_component(
            actor_membership=self.owner,
            component_id=self.basic.pk,
            code="BASE",
            name="Base Pay",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Basic Salary",
        )
        update_overtime_policy(
            actor_membership=self.owner,
            policy_id=self.policy.pk,
            code="OT15",
            name="Updated OT",
            base_component_id=self.basic.pk,
            divisor="208",
            multiplier="2",
        )

        line.refresh_from_db()
        structure.refresh_from_db()
        self.assertEqual(line.component_code, "BASIC")
        self.assertEqual(line.component_name, "Basic Salary")
        self.assertEqual(structure.overtime_policy_name, "Standard OT")
        self.assertEqual(structure.overtime_divisor, Decimal("240.0000"))
        self.assertEqual(structure.overtime_multiplier, Decimal("1.5000"))

    def test_effective_change_closes_previous_structure(self):
        first = self._assign(date(2025, 1, 1))
        second = self._assign(date(2026, 1, 1), basic="4500")
        first.refresh_from_db()
        self.assertEqual(first.effective_to, date(2025, 12, 31))
        self.assertIsNone(second.effective_to)
        self.assertEqual(SalaryStructure.objects.filter(employee=self.employee).count(), 2)
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                action="internal.salary_structure.closed",
                object_id=str(first.pk),
            ).exists()
        )

    def test_future_insertion_preserves_next_structure_boundary(self):
        first = self._assign(date(2025, 1, 1))
        third = self._assign(date(2027, 1, 1), basic="5000")
        middle = self._assign(date(2026, 1, 1), basic="4500")
        first.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(first.effective_to, date(2025, 12, 31))
        self.assertEqual(middle.effective_to, date(2026, 12, 31))
        self.assertIsNone(third.effective_to)

    def test_duplicate_effective_date_is_rejected(self):
        self._assign(date(2025, 1, 1))
        with self.assertRaises(ValidationError):
            self._assign(date(2025, 1, 1), basic="5000")

    def test_basic_salary_mapping_and_positive_amount_are_required(self):
        with self.assertRaises(ValidationError):
            assign_employee_salary_structure(
                actor_membership=self.owner,
                employee_id=self.employee.pk,
                effective_from=date(2025, 1, 1),
                components=[{"component_id": self.housing.pk, "amount": "1000"}],
            )
        with self.assertRaises(ValidationError):
            self._assign(date(2025, 1, 1), basic="0")

    def test_only_one_active_basic_salary_component_is_allowed(self):
        with self.assertRaises(ValidationError):
            create_salary_component(
                actor_membership=self.owner,
                code="BASIC2",
                name="Second Basic",
                category="Earning",
                recurrence="Recurring",
                calculation="Fixed Amount",
                wps_mapping="Basic Salary",
            )


    def test_overtime_multiplier_must_be_positive(self):
        with self.assertRaises(ValidationError):
            create_overtime_policy(
                actor_membership=self.owner,
                code="OTZERO",
                name="Zero Overtime",
                base_component_id=self.basic.pk,
                divisor="240",
                multiplier="0",
            )

    def test_active_overtime_base_component_cannot_be_deactivated(self):
        with self.assertRaises(ValidationError):
            update_salary_component(
                actor_membership=self.owner,
                component_id=self.basic.pk,
                code=self.basic.code,
                name=self.basic.name,
                category="Earning",
                recurrence="Recurring",
                calculation="Fixed Amount",
                wps_mapping="Basic Salary",
                is_active=False,
            )

    def test_overtime_policy_requires_an_active_base_component(self):
        inactive = create_salary_component(
            actor_membership=self.owner,
            code="OTBASE",
            name="Inactive OT Base",
            category="Earning",
            recurrence="Recurring",
            calculation="Fixed Amount",
            wps_mapping="Other Earnings",
            is_active=False,
        )
        with self.assertRaises(ValidationError):
            create_overtime_policy(
                actor_membership=self.owner,
                code="OT-INACTIVE",
                name="Invalid Overtime",
                base_component_id=inactive.pk,
                divisor="240",
                multiplier="1.5",
            )


    def test_secondary_configuration_archive_restore_and_delete_unused(self):
        component = create_salary_component(
            actor_membership=self.owner, code="TEMP", name="Temporary Allowance",
            category="Earning", recurrence="Variable", calculation="Manual Amount", wps_mapping="Other Earnings",
        )
        archived = archive_salary_component(actor_membership=self.owner, component_id=component.pk, reason="No longer used")
        self.assertIsNotNone(archived.archived_at)
        self.assertFalse(archived.is_active)
        with self.assertRaises(ValidationError):
            update_salary_component(
                actor_membership=self.owner, component_id=component.pk, code="TEMP", name="Temporary Allowance",
                category="Earning", recurrence="Variable", calculation="Manual Amount", wps_mapping="Other Earnings",
            )
        restored = restore_salary_component_archive(actor_membership=self.owner, component_id=component.pk)
        self.assertIsNone(restored.archived_at)
        self.assertFalse(restored.is_active)
        deleted_id = delete_unused_salary_component(actor_membership=self.owner, component_id=component.pk, confirmation="TEMP")
        self.assertEqual(deleted_id, str(component.pk))

    def test_used_salary_configuration_must_be_archived_not_deleted(self):
        self._assign()
        with self.assertRaises(ValidationError):
            delete_unused_salary_component(actor_membership=self.owner, component_id=self.housing.pk, confirmation=self.housing.code)
        with self.assertRaises(ValidationError):
            delete_unused_overtime_policy(actor_membership=self.owner, policy_id=self.policy.pk, confirmation=self.policy.code)

    def test_active_overtime_dependency_blocks_base_component_archive(self):
        with self.assertRaises(ValidationError):
            archive_salary_component(actor_membership=self.owner, component_id=self.basic.pk, reason="Retire old base")
        archived_policy = archive_overtime_policy(actor_membership=self.owner, policy_id=self.policy.pk, reason="Replace OT formula")
        self.assertIsNotNone(archived_policy.archived_at)
        restored = restore_overtime_policy_archive(actor_membership=self.owner, policy_id=self.policy.pk)
        self.assertFalse(restored.is_active)
        archived_component = archive_salary_component(actor_membership=self.owner, component_id=self.basic.pk, reason="Retire old base")
        self.assertIsNotNone(archived_component.archived_at)

    def test_reviewer_cannot_modify_salary_setup(self):
        reviewer_user = User.objects.create_user(username="salary-reviewer")
        reviewer = CompanyMembership.objects.create(
            company=self.company,
            user=reviewer_user,
            role=AccessRole.FINANCE_REVIEWER,
        )
        with self.assertRaises(PermissionDenied):
            create_salary_component(
                actor_membership=reviewer,
                code="BONUS",
                name="Bonus",
                category="Earning",
                recurrence="Variable",
                calculation="Manual Amount",
            )

    def test_salary_changes_are_audited(self):
        structure = self._assign()
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                action="internal.salary_structure.assigned",
                object_id=str(structure.pk),
            ).exists()
        )
