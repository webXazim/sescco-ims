import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.internal_payroll.models import Branch, Department, InternalEmployee
from apps.internal_payroll.services import create_branch, create_department, create_employee


class InternalOrganizationApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme-api")
        self.user = User.objects.create_user(username="payroll", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(self.user)
        self.branch = create_branch(actor_membership=self.membership, code="HQ", name="Head Office")
        self.department = create_department(actor_membership=self.membership, code="OPS", name="Operations")

    def test_create_employee_endpoint_persists_master(self):
        response = self.client.post(
            reverse("internal_payroll:employees-api"),
            data=json.dumps(
                {
                    "employee_number": "0001",
                    "full_name": "API Employee",
                    "joining_date": date(2020, 1, 1).isoformat(),
                    "branch_id": str(self.branch.pk),
                    "department_id": str(self.department.pk),
                    "position": "Supervisor",
                    "status": "Active",
                    "national_id": "",
                    "phone": "",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["employee"]["name"], "API Employee")
        self.assertEqual(payload["employee"]["branchId"], str(self.branch.pk))
        self.assertEqual(len(payload["history"]), 1)

    def test_branch_list_supports_search_sort_and_pagination(self):
        create_branch(actor_membership=self.membership, code="BR-B", name="Beta Office")
        create_branch(actor_membership=self.membership, code="BR-A", name="Alpha Office")
        response = self.client.get(
            reverse("internal_payroll:branches-api"),
            {"q": "Office", "sort": "name", "direction": "desc", "page": 1, "page_size": 1},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["name"], "Beta Office")
        self.assertEqual(payload["meta"]["count"], 2)
        self.assertEqual(payload["meta"]["pageSize"], 1)
        self.assertEqual(payload["meta"]["sort"], "name")
        self.assertEqual(payload["meta"]["direction"], "desc")

    def test_branch_list_rejects_unknown_sort(self):
        response = self.client.get(reverse("internal_payroll:branches-api"), {"sort": "unsafe"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_list_branches_is_company_scoped(self):
        other_company = Company.objects.create(name="Other", slug="other-api")
        other_user = User.objects.create_user(username="other")
        other_membership = CompanyMembership.objects.create(company=other_company, user=other_user, role=AccessRole.OWNER)
        create_branch(actor_membership=other_membership, code="OTHER", name="Other Branch")

        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 200)
        codes = {row["code"] for row in response.json()["results"]}
        self.assertEqual(codes, {"HQ"})

    def test_unauthenticated_api_request_returns_json_401(self):
        self.client.logout()
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["ok"], False)

    def test_operations_admin_does_not_gain_payroll_access_from_merge(self):
        operations_user = User.objects.create_user(username="operations-only", password="test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=operations_user,
            role=AccessRole.OPERATIONS_ADMIN,
        )
        self.client.force_login(operations_user)
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)

    def test_role_without_internal_workspace_returns_json_403(self):
        rental_user = User.objects.create_user(username="rental-only", password="test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=rental_user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(rental_user)
        response = self.client.get(reverse("internal_payroll:branches-api"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["ok"], False)
    def _create_employee(self, number="0001", name="Lifecycle Employee"):
        return create_employee(
            actor_membership=self.membership,
            employee_number=number,
            full_name=name,
            joining_date=date(2020, 1, 1),
            branch_id=self.branch.pk,
            department_id=self.department.pk,
            position="Supervisor",
        )


    def test_branch_archive_restore_delete_unused_and_archived_filter(self):
        lifecycle_url = reverse("internal_payroll:branch-lifecycle-api", kwargs={"branch_id": self.branch.pk})
        archived = self.client.post(lifecycle_url, data=json.dumps({"action":"archive","reason":"Unused office"}), content_type="application/json")
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["branch"]["status"], "Archived")
        listing = self.client.get(reverse("internal_payroll:branches-api"), {"status":"archived"})
        self.assertIn(str(self.branch.pk), {row["id"] for row in listing.json()["results"]})
        restored = self.client.post(lifecycle_url, data=json.dumps({"action":"restore_archive"}), content_type="application/json")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["branch"]["status"], "Inactive")
        unused = create_branch(actor_membership=self.membership, code="TMP", name="Temp Office")
        deleted = self.client.delete(reverse("internal_payroll:branch-detail-api", kwargs={"branch_id":unused.pk}), data=json.dumps({"confirmation":"TMP","reason":"Mistake"}), content_type="application/json")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Branch.objects.filter(pk=unused.pk).exists())

    def test_department_delete_is_blocked_after_employee_assignment(self):
        self._create_employee()
        response = self.client.delete(reverse("internal_payroll:department-detail-api", kwargs={"department_id": self.department.pk}), data=json.dumps({"confirmation":self.department.code}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Department.objects.filter(pk=self.department.pk).exists())

    def test_employee_lifecycle_termination_and_archive_filters(self):
        employee = self._create_employee()
        lifecycle_url = reverse("internal_payroll:employee-lifecycle-api", kwargs={"employee_id": employee.pk})
        response = self.client.post(
            lifecycle_url,
            data=json.dumps({"action": "terminate", "effective_date": date.today().isoformat(), "reason": "Contract ended"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["employee"]["status"], "Terminated")

        response = self.client.post(
            lifecycle_url,
            data=json.dumps({"action": "archive", "reason": "Closed employment file"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["employee"]["archived"])

        current = self.client.get(reverse("internal_payroll:employees-api"))
        self.assertEqual(current.status_code, 200)
        self.assertNotIn(str(employee.pk), {row["id"] for row in current.json()["results"]})

        archived = self.client.get(reverse("internal_payroll:employees-api"), {"archived": "archived"})
        self.assertEqual(archived.status_code, 200)
        self.assertIn(str(employee.pk), {row["id"] for row in archived.json()["results"]})

    def test_employee_lifecycle_leave_requires_reason(self):
        employee = self._create_employee()
        response = self.client.post(
            reverse("internal_payroll:employee-lifecycle-api", kwargs={"employee_id": employee.pk}),
            data=json.dumps({"action": "leave", "reason": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_unused_employee_delete_requires_typed_employee_number(self):
        employee = self._create_employee()
        detail_url = reverse("internal_payroll:employee-detail-api", kwargs={"employee_id": employee.pk})
        blocked = self.client.delete(
            detail_url, data=json.dumps({"confirmation": "WRONG", "reason": "Duplicate"}), content_type="application/json"
        )
        self.assertEqual(blocked.status_code, 400)
        deleted = self.client.delete(
            detail_url, data=json.dumps({"confirmation": employee.employee_number, "reason": "Duplicate onboarding"}), content_type="application/json"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(InternalEmployee.objects.filter(pk=employee.pk).exists())

