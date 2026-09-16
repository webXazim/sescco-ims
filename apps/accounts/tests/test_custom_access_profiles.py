from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import create_access_profile
from apps.accounts.models import AccessProfile, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company


class CustomAccessProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Page Access Co", slug="page-access-co")
        self.owner_user = User.objects.create_user(username="page-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)

    def _create_viewer(self, permissions):
        profile = create_access_profile(
            actor_membership=self.owner,
            payload={
                "name": "Internal Attendance Viewer",
                "description": "Only the selected Internal pages are visible.",
                "permissions": [permission.value if isinstance(permission, AccessPermission) else permission for permission in permissions],
            },
        )
        user = get_user_model().objects.create_user(username="narrow-viewer", password="ViewerPass!2026")
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.CUSTOM,
            access_profile=profile,
        )
        return user, membership, profile

    def test_owner_can_create_custom_profile_with_exact_permissions_and_audit(self):
        profile = create_access_profile(
            actor_membership=self.owner,
            payload={
                "name": "Employee + Attendance View",
                "description": "View only.",
                "permissions": [
                    AccessPermission.INTERNAL_EMPLOYEES_VIEW.value,
                    AccessPermission.INTERNAL_ATTENDANCE_VIEW.value,
                ],
            },
        )
        self.assertFalse(profile.is_system)
        self.assertTrue(profile.key.startswith("custom-employee-attendance-view-"))
        self.assertEqual(
            set(profile.permission_grants.values_list("permission", flat=True)),
            {AccessPermission.INTERNAL_EMPLOYEES_VIEW.value, AccessPermission.INTERNAL_ATTENDANCE_VIEW.value},
        )
        self.assertTrue(AuditEvent.objects.filter(action="access.profile.created", object_id=str(profile.pk)).exists())

    def test_profile_api_creates_custom_view_only_profile(self):
        self.client.force_login(self.owner_user)
        response = self.client.post(
            reverse("accounts:access-profiles-api"),
            data=json.dumps({
                "name": "Rental Workers Read Only",
                "permissions": [AccessPermission.RENTAL_WORKERS_VIEW.value],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertFalse(body["profile"]["system"])
        self.assertEqual(body["profile"]["permissions"], [AccessPermission.RENTAL_WORKERS_VIEW.value])

    def test_built_in_profile_cannot_be_modified(self):
        self.client.force_login(self.owner_user)
        system_profile = AccessProfile.objects.get(company=self.company, key="role-owner")
        response = self.client.patch(
            reverse("accounts:access-profile-detail-api", kwargs={"profile_id": system_profile.pk}),
            data=json.dumps({"name": "Changed"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_page_level_viewer_can_read_only_selected_internal_pages(self):
        user, _membership, _profile = self._create_viewer([
            AccessPermission.INTERNAL_EMPLOYEES_VIEW,
            AccessPermission.INTERNAL_ATTENDANCE_VIEW,
        ])
        self.client.force_login(user)

        employees = self.client.get(reverse("internal_payroll:employees-api"))
        attendance = self.client.get(reverse("internal_payroll:attendance-api"), {"period": "2026-09"})
        payroll = self.client.get(reverse("internal_payroll:payroll-api"), {"period": "2026-09"})
        salary = self.client.get(reverse("internal_payroll:salary-components-api"))

        self.assertEqual(employees.status_code, 200)
        self.assertEqual(attendance.status_code, 200)
        self.assertEqual(payroll.status_code, 403)
        self.assertEqual(salary.status_code, 403)

    def test_view_only_profile_cannot_mutate_a_page_it_can_read(self):
        user, _membership, _profile = self._create_viewer([AccessPermission.INTERNAL_EMPLOYEES_VIEW])
        self.client.force_login(user)
        response = self.client.post(
            reverse("internal_payroll:employees-api"),
            data=json.dumps({"employee_number": "BLOCKED", "full_name": "Blocked Mutation"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_employee_only_viewer_bootstrap_does_not_receive_attendance_roster(self):
        user, _membership, _profile = self._create_viewer([AccessPermission.INTERNAL_EMPLOYEES_VIEW])
        self.client.force_login(user)
        response = self.client.get(reverse("core:payroll"))
        self.assertEqual(response.status_code, 200)
        attendance = response.context["attendance_context"]
        self.assertEqual(attendance["roster"], [])
        self.assertEqual(attendance["records"], {})
        self.assertEqual(attendance["overtime"], {})
