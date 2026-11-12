from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
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

    def _inventory_members(self):
        members = []
        for index in range(3):
            user = get_user_model().objects.create_user(
                username=f"inventory-assignee-{index}", password="AssignmentPass!2026"
            )
            members.append(CompanyMembership.objects.create(
                company=self.company, user=user, role=AccessRole.INVENTORY_MANAGER
            ))
        return members

    def _clone_payload(self, source, **changes):
        payload = {
            "name": "Inventory Manager (Custom)",
            "description": "Inventory plus approval",
            "permissions": [
                AccessPermission.INVENTORY_STOCK_VIEW.value,
                AccessPermission.INVENTORY_STOCK_APPROVE.value,
            ],
            "sourceProfileId": str(source.pk),
            "assignmentMode": "none",
        }
        payload.update(changes)
        return payload

    def test_clone_step_roster_lists_only_assignees_of_source_profile(self):
        members = self._inventory_members()
        source = members[0].access_profile
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("accounts:access-profiles-api"), {"assigned_to": str(source.pk)})
        self.assertEqual(response.status_code, 200)
        rows = response.json()["assignedUsersForClone"]
        self.assertEqual({row["membershipId"] for row in rows}, {str(m.pk) for m in members})
        self.assertEqual({row["username"] for row in rows}, {m.user.username for m in members})

    def test_clone_keep_does_not_change_any_assigned_user(self):
        members = self._inventory_members()
        source = members[0].access_profile
        profile = create_access_profile(actor_membership=self.owner, payload=self._clone_payload(source))
        self.assertFalse(profile.is_system)
        self.assertEqual(profile.memberships.count(), 0)
        self.assertEqual(CompanyMembership.objects.filter(access_profile=source).count(), 3)

    def test_clone_selected_moves_only_chosen_users_and_preserves_scopes(self):
        members = self._inventory_members()
        source = members[0].access_profile
        members[0].project_scope_mode = "none"
        members[0].save(update_fields=("project_scope_mode", "updated_at"))
        initial_version = members[0].user.security_version
        profile = create_access_profile(actor_membership=self.owner, payload=self._clone_payload(
            source, assignmentMode="selected", membershipIds=[str(members[0].pk), str(members[2].pk)]
        ))
        members[0].refresh_from_db()
        members[1].refresh_from_db()
        members[2].refresh_from_db()
        self.assertEqual(members[0].access_profile_id, profile.pk)
        self.assertEqual(members[2].access_profile_id, profile.pk)
        self.assertEqual(members[1].access_profile_id, source.pk)
        self.assertEqual(members[0].role, AccessRole.CUSTOM)
        self.assertEqual(members[0].project_scope_mode, "none")
        members[0].user.refresh_from_db()
        self.assertEqual(members[0].user.security_version, initial_version + 1)
        events = AuditEvent.objects.filter(action="access.user.updated", metadata__profile_clone_user_reassignment=True)
        self.assertEqual(events.count(), 2)
        for event in events:
            self.assertIn("scopes", event.before)
            self.assertIn("scopes", event.after)
            self.assertEqual(event.before["accessProfileId"], str(source.pk))
            self.assertEqual(event.after["accessProfileId"], str(profile.pk))

    def test_clone_all_moves_full_reviewed_roster(self):
        members = self._inventory_members()
        source = members[0].access_profile
        self.client.force_login(self.owner_user)
        response = self.client.post(reverse("accounts:access-profiles-api"), data=json.dumps(
            self._clone_payload(source, assignmentMode="all", expectedMembershipIds=[str(m.pk) for m in members])
        ), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        profile = AccessProfile.objects.get(pk=response.json()["profile"]["id"])
        self.assertEqual(profile.memberships.count(), 3)
        self.assertEqual(source.memberships.count(), 0)

    def test_clone_stale_all_roster_aborts_creation(self):
        members = self._inventory_members()
        source = members[0].access_profile
        with self.assertRaises(ValidationError):
            create_access_profile(actor_membership=self.owner, payload=self._clone_payload(
                source, assignmentMode="all", expectedMembershipIds=[str(members[0].pk)]
            ))
        self.assertFalse(AccessProfile.objects.filter(company=self.company, name="Inventory Manager (Custom)").exists())
        self.assertEqual(source.memberships.count(), 3)

    def test_clone_rejects_foreign_or_changed_membership(self):
        members = self._inventory_members()
        source = members[0].access_profile
        other_company = Company.objects.create(name="Other Access Co", slug="other-access-co")
        other_user = get_user_model().objects.create_user(username="outside-company", password="AssignmentPass!2026")
        foreign = CompanyMembership.objects.create(company=other_company, user=other_user, role=AccessRole.INVENTORY_MANAGER)
        for membership_id in (str(foreign.pk), str(self.owner.pk)):
            with self.assertRaises(ValidationError):
                create_access_profile(actor_membership=self.owner, payload=self._clone_payload(
                    source, assignmentMode="selected", membershipIds=[membership_id]
                ))
        self.assertFalse(AccessProfile.objects.filter(company=self.company, name="Inventory Manager (Custom)").exists())

    def test_clone_cannot_change_own_profile_even_with_bulk_all(self):
        admin_user = get_user_model().objects.create_user(username="clone-admin", password="AssignmentPass!2026")
        admin = CompanyMembership.objects.create(
            company=self.company, user=admin_user, role=AccessRole.ACCESS_ADMINISTRATOR
        )
        with self.assertRaises(PermissionDenied):
            create_access_profile(actor_membership=admin, payload=self._clone_payload(
                admin.access_profile, assignmentMode="all", expectedMembershipIds=[str(admin.pk)]
            ))

    def test_clone_refuses_owner_profile_reassignment(self):
        with self.assertRaises(PermissionDenied):
            create_access_profile(actor_membership=self.owner, payload=self._clone_payload(
                self.owner.access_profile, assignmentMode="all", expectedMembershipIds=[str(self.owner.pk)]
            ))

    def test_clone_reassignment_requires_user_management_permission(self):
        members = self._inventory_members()
        source = members[0].access_profile
        custom = create_access_profile(actor_membership=self.owner, payload={
            "name": "Profile Builder Only",
            "permissions": [AccessPermission.ACCESS_PROFILES_VIEW.value, AccessPermission.ACCESS_PROFILES_MANAGE.value],
        })
        actor_user = get_user_model().objects.create_user(username="profiles-only", password="AssignmentPass!2026")
        actor = CompanyMembership.objects.create(company=self.company, user=actor_user, role=AccessRole.CUSTOM, access_profile=custom)
        with self.assertRaises(PermissionDenied):
            create_access_profile(actor_membership=actor, payload=self._clone_payload(
                source, assignmentMode="selected", membershipIds=[str(members[0].pk)]
            ))
        self.client.force_login(actor_user)
        response = self.client.get(reverse("accounts:access-profiles-api"), {"assigned_to": str(source.pk)})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(AccessProfile.objects.filter(company=self.company, name="Inventory Manager (Custom)").exists())

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
