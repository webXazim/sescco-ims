from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import create_access_profile
from apps.accounts.models import CompanyMembership, MembershipBranchScope, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.services import create_branch, create_department, create_employee


class CrossModuleAccessLeakClosureTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Leak Closure Co", slug="leak-closure-co")
        self.owner_user = User.objects.create_user(username="leak-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.branch_a = create_branch(actor_membership=self.owner, code="A", name="Branch A")
        self.branch_b = create_branch(actor_membership=self.owner, code="B", name="Branch B")
        self.department = create_department(actor_membership=self.owner, code="OPS", name="Operations")
        self.employee_a = create_employee(
            actor_membership=self.owner, employee_number="A-001", full_name="Allowed Employee",
            joining_date=date(2025, 1, 1), branch_id=self.branch_a.pk, department_id=self.department.pk, position="Clerk",
        )
        self.employee_b = create_employee(
            actor_membership=self.owner, employee_number="B-001", full_name="Blocked Employee",
            joining_date=date(2025, 1, 1), branch_id=self.branch_b.pk, department_id=self.department.pk, position="Clerk",
        )

    def _viewer(self, name: str, permissions, *, branch=None):
        profile = create_access_profile(
            actor_membership=self.owner,
            payload={"name": name, "permissions": [p.value if isinstance(p, AccessPermission) else p for p in permissions]},
        )
        user = get_user_model().objects.create_user(username=name.lower().replace(" ", "-"), password="ViewerPass!2026")
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile,
            branch_scope_mode=ScopeMode.SELECTED if branch else ScopeMode.ALL,
        )
        if branch:
            MembershipBranchScope.objects.create(membership=membership, branch=branch)
        return user, membership

    def test_employee_only_profile_does_not_receive_attendance_payroll_payment_or_audit_profile_data(self):
        user, _membership = self._viewer("Employee Only", [AccessPermission.INTERNAL_EMPLOYEES_VIEW], branch=self.branch_a)
        self.client.force_login(user)
        response = self.client.get(
            reverse("internal_payroll:employee-profile-api", kwargs={"employee_id": self.employee_a.pk}),
            {"period": "2026-09"},
        )
        self.assertEqual(response.status_code, 200)
        profile = response.json()["profile"]
        self.assertIsNone(profile["attendance"])
        self.assertEqual(profile["adjustments"], [])
        self.assertEqual(profile["payrollHistory"], [])
        self.assertEqual(profile["activity"], [])

    def test_branch_scoped_employee_list_hides_other_branch(self):
        user, _membership = self._viewer("Branch Employee Viewer", [AccessPermission.INTERNAL_EMPLOYEES_VIEW], branch=self.branch_a)
        self.client.force_login(user)
        response = self.client.get(reverse("internal_payroll:employees-api"), {"page": 1, "page_size": 25})
        self.assertEqual(response.status_code, 200)
        ids = {row["employeeId"] for row in response.json()["results"]}
        self.assertIn("A-001", ids)
        self.assertNotIn("B-001", ids)

    def test_branch_scoped_employee_deep_link_hides_other_branch(self):
        user, _membership = self._viewer("Branch Deep Link Viewer", [AccessPermission.INTERNAL_EMPLOYEES_VIEW], branch=self.branch_a)
        self.client.force_login(user)
        response = self.client.get(
            reverse("internal_payroll:employee-profile-api", kwargs={"employee_id": self.employee_b.pk}),
            {"period": "2026-09"},
        )
        self.assertEqual(response.status_code, 404)

    def test_branch_scoped_payroll_bootstrap_hides_other_branch(self):
        user, _membership = self._viewer(
            "Scoped Bootstrap Viewer",
            [AccessPermission.INTERNAL_EMPLOYEES_VIEW],
            branch=self.branch_a,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("core:payroll"))
        self.assertEqual(response.status_code, 200)

        bootstrap = response.context["internal_master_context"]
        branch_ids = {row["id"] for row in bootstrap["branches"]}
        employee_numbers = {row["employeeNumber"] for row in bootstrap["employees"]}
        self.assertIn(str(self.branch_a.pk), branch_ids)
        self.assertNotIn(str(self.branch_b.pk), branch_ids)
        self.assertIn("A-001", employee_numbers)
        self.assertNotIn("B-001", employee_numbers)

    def test_generic_reports_permission_does_not_unlock_wps_data(self):
        user, _membership = self._viewer("Reports Only", [AccessPermission.INTERNAL_REPORTS_VIEW])
        self.client.force_login(user)
        response = self.client.get(reverse("core:reports-api"), {
            "workspace": "internal", "type": "wps", "period": "2026-09",
        })
        self.assertEqual(response.status_code, 403)

    def test_generic_reports_permission_does_not_unlock_payments_data(self):
        user, _membership = self._viewer("Reports Payment Block", [AccessPermission.INTERNAL_REPORTS_VIEW])
        self.client.force_login(user)
        response = self.client.get(reverse("core:reports-api"), {
            "workspace": "internal", "type": "payments", "period": "2026-09",
        })
        self.assertEqual(response.status_code, 403)

    def test_access_administrator_cannot_infer_management_financial_overview(self):
        user, _membership = self._viewer("Access Admin Narrow", [AccessPermission.ACCESS_USERS_VIEW])
        self.client.force_login(user)
        response = self.client.get(reverse("core:management-summary-api"), {"period": "2026-09"})
        self.assertEqual(response.status_code, 403)

    def test_scoped_management_audit_fails_closed(self):
        user, _membership = self._viewer("Scoped Audit", [AccessPermission.ACCESS_AUDIT_VIEW], branch=self.branch_a)
        self.client.force_login(user)
        response = self.client.get(reverse("core:management-audit-api"))
        self.assertEqual(response.status_code, 403)

    def test_department_counts_are_limited_to_assigned_branch(self):
        user, _membership = self._viewer("Scoped Organization", [AccessPermission.INTERNAL_ORGANIZATION_VIEW], branch=self.branch_a)
        self.client.force_login(user)
        response = self.client.get(reverse("internal_payroll:departments-api"), {"page": 1, "page_size": 25})
        self.assertEqual(response.status_code, 200)
        operations = next(row for row in response.json()["results"] if row["code"] == "OPS")
        self.assertEqual(operations["activeEmployeeCount"], 1)
