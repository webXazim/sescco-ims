from django.test import SimpleTestCase

from apps.accounts.access_catalog import AccessPermission, permissions_for_legacy_role
from apps.accounts.roles import AccessRole


class InternalFinancePermissionDecompositionTests(SimpleTestCase):
    def _permissions(self, role):
        return {item.value for item in permissions_for_legacy_role(role)}

    def test_internal_payroll_officer_prepares_but_cannot_review_or_final_approve(self):
        permissions = self._permissions(AccessRole.INTERNAL_PAYROLL_OFFICER)
        self.assertIn(AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE.value, permissions)
        self.assertIn(AccessPermission.INTERNAL_ATTENDANCE_SUBMIT.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYMENTS_EXECUTE.value, permissions)

    def test_finance_reviewer_can_review_but_not_final_approve(self):
        permissions = self._permissions(AccessRole.FINANCE_REVIEWER)
        self.assertIn(AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW.value, permissions)
        self.assertIn(AccessPermission.INTERNAL_ATTENDANCE_APPROVE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYMENTS_EXECUTE.value, permissions)

    def test_finance_manager_can_final_approve_and_execute_without_payroll_preparation(self):
        permissions = self._permissions(AccessRole.FINANCE_MANAGER)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW.value, permissions)
        self.assertIn(AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE.value, permissions)
        self.assertIn(AccessPermission.INTERNAL_PAYMENTS_EXECUTE.value, permissions)
        self.assertIn(AccessPermission.INTERNAL_WPS_EXPORT.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_SALARY_SETUP_MANAGE.value, permissions)
        self.assertNotIn(AccessPermission.INTERNAL_EMPLOYEES_MANAGE.value, permissions)
