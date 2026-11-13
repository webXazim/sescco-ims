"""U02 project-team permissions, atomic replacement and company/project isolation."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent, Company
from apps.projects.models import Project
from apps.project_pulse.models import PulseProjectTeamMember
from apps.project_pulse.services import assign_team_member, remove_team_member


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ProjectTeamTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Pulse Projects", slug="pulse-projects")
        self.other = Company.objects.create(name="Pulse Other", slug="pulse-other")
        self.owner_user = User.objects.create_user(username="pulse-team-owner", password="Strong2026!")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.project = Project.objects.create(company=self.company, code="PP-01", name="Pulse Team Project")
        self.second = Project.objects.create(company=self.company, code="PP-02", name="Other Project")
        self.foreign = Project.objects.create(company=self.other, code="PP-03", name="Secret Project")

    def _member(self, name, *, company=None, perms=None, scope=ScopeMode.ALL, projects=()):
        company = company or self.company
        if perms is None:
            perms = ("pulse.overview.view", "pulse.projects.view", "pulse.team.view")
        User = get_user_model()
        user = User.objects.create_user(username=name, password="Strong2026!")
        profile = AccessProfile.objects.create(company=company, key=f"custom-{name}", name=name)
        for permission in perms:
            AccessProfilePermission.objects.create(profile=profile, permission=permission)
        membership = CompanyMembership.objects.create(
            company=company, user=user, role=AccessRole.CUSTOM,
            access_profile=profile, project_scope_mode=scope,
        )
        if scope == ScopeMode.SELECTED:
            for project in projects:
                membership.project_scopes.create(project=project)
        return user, membership

    def _assign_url(self, project=None):
        return reverse("project_pulse:team_assign", args=[(project or self.project).code])

    def test_owner_grant_and_profile_permission_dependencies(self):
        self.assertTrue(membership_has_permission(self.owner, AccessPermission.PULSE_TEAM_VIEW))
        self.assertTrue(membership_has_permission(self.owner, AccessPermission.PULSE_TEAM_MANAGE))
        self.assertEqual({entry["code"] for entry in permission_catalog() if entry["category"] == "Project Pulse"}, {
            "pulse.overview.view", "pulse.projects.view", "pulse.team.view", "pulse.team.manage",
            "pulse.categories.view", "pulse.categories.manage", "pulse.tasks.view", "pulse.tasks.manage",
        })
        for values in (["pulse.team.view"], ["pulse.overview.view", "pulse.team.manage"]):
            with self.assertRaises(ValidationError):
                _clean_permissions(values)
        self.assertEqual(len(_clean_permissions([
            "pulse.overview.view", "pulse.projects.view", "pulse.team.view", "pulse.team.manage",
        ])), 4)

    def test_owner_adds_team_member_and_manager_without_inventory_authority(self):
        member_user, member = self._member("pulse-worker")
        self.client.force_login(self.owner_user)
        res = self.client.post(self._assign_url(), {"membership_id": str(member.pk), "role": "manager"})
        self.assertRedirects(res, reverse("project_pulse:project_team", args=[self.project.code]))
        item = PulseProjectTeamMember.objects.get(project=self.project, membership=member)
        self.assertEqual(item.role, "manager")
        self.assertTrue(item.is_active)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.inventory_manager)
        self.assertEqual(self.client.get(reverse("project_pulse:project_team", args=[self.project.code])).status_code, 200)
        self.assertContains(self.client.get(reverse("project_pulse:project_team", args=[self.project.code])), "pulse-worker")
        self.assertTrue(AuditEvent.objects.filter(action="pulse.team.assigned", company=self.company).exists())

    def test_manager_replacement_demotes_existing_manager(self):
        _, first = self._member("manager-a")
        _, second = self._member("manager-b")
        assign_team_member(actor=self.owner, project_id=self.project.id, member_id=first.pk, role="manager")
        assign_team_member(actor=self.owner, project_id=self.project.id, member_id=second.pk, role="manager")
        assigned = list(PulseProjectTeamMember.objects.filter(project=self.project, is_active=True))
        self.assertEqual(len(assigned), 2)
        self.assertEqual(len([record for record in assigned if record.role == "manager"]), 1)
        self.assertEqual(PulseProjectTeamMember.objects.get(membership=first).role, "member")
        self.assertEqual(PulseProjectTeamMember.objects.get(membership=second).role, "manager")

    def test_assignment_removed_and_restored_without_duplicate_row(self):
        _, member = self._member("worker-reentry")
        record = assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        remove_team_member(actor=self.owner, project_id=self.project.pk, team_member_id=record.pk)
        record.refresh_from_db()
        self.assertFalse(record.is_active)
        self.assertIsNotNone(record.ended_at)
        updated = assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        self.assertEqual(updated.pk, record.pk)
        self.assertTrue(updated.is_active)
        self.assertIsNone(updated.ended_at)
        self.assertEqual(PulseProjectTeamMember.objects.filter(project=self.project, membership=member).count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action="pulse.team.unassigned").exists())

    def test_cross_company_or_out_of_scope_membership_rejected(self):
        _, foreign_member = self._member("foreign-pulse-worker", company=self.other)
        _, out_of_scope = self._member("out-of-scope-worker", scope=ScopeMode.SELECTED, projects=(self.second,))
        for member in (foreign_member, out_of_scope):
            with self.subTest(member=member):
                with self.assertRaises(ValidationError):
                    assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        self.assertEqual(PulseProjectTeamMember.objects.count(), 0)
        with self.assertRaises(Http404):
            assign_team_member(actor=self.owner, project_id=self.foreign.pk, member_id=foreign_member.pk, role="member")

    def test_inactive_or_nonpulse_user_rejected(self):
        _, no_pulse = self._member("inventory-user", perms=("inventory.stock.view",))
        _, inactive = self._member("inactive-pulse")
        inactive.is_active = False
        inactive.save()
        for member in (no_pulse, inactive):
            with self.assertRaises(ValidationError):
                assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")

    def test_team_view_only_cannot_change_assignments(self):
        user, viewer = self._member("team-viewer")
        _, candidate = self._member("team-candidate")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("project_pulse:project_team", args=[self.project.code])).status_code, 200)
        self.assertEqual(self.client.post(self._assign_url(), {
            "membership_id": str(candidate.pk), "role": "manager",
        }).status_code, 403)
        self.assertEqual(PulseProjectTeamMember.objects.count(), 0)
        with self.assertRaises(PermissionDenied):
            assign_team_member(actor=viewer, project_id=self.project.pk, member_id=candidate.pk, role="member")

    def test_no_team_view_cannot_see_team_members(self):
        user, _ = self._member("project-only", perms=("pulse.overview.view", "pulse.projects.view"))
        self.client.force_login(user)
        detail = self.client.get(reverse("project_pulse:project_detail", args=[self.project.code]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Project Pulse team")
        self.assertEqual(self.client.get(reverse("project_pulse:project_team", args=[self.project.code])).status_code, 403)

    def test_scoped_manager_cannot_assign_to_another_project(self):
        user, scoped_manager = self._member(
            "scoped-team-manager", scope=ScopeMode.SELECTED, projects=(self.project,),
            perms=("pulse.overview.view", "pulse.projects.view", "pulse.team.view", "pulse.team.manage"),
        )
        _, candidate = self._member("scoped-candidate")
        self.client.force_login(user)
        self.assertEqual(self.client.post(self._assign_url(self.second), {
            "membership_id": str(candidate.pk), "role": "member",
        }).status_code, 404)
        self.assertEqual(self.client.post(self._assign_url(), {
            "membership_id": str(candidate.pk), "role": "member",
        }).status_code, 302)
        self.assertEqual(PulseProjectTeamMember.objects.count(), 1)
        self.assertEqual(scoped_manager.project_scope_mode, ScopeMode.SELECTED)

    def test_closed_projects_are_read_only_and_invalid_role_rejected(self):
        _, member = self._member("closed-worker")
        with self.assertRaises(ValidationError):
            assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="chief")
        Project.objects.filter(pk=self.project.pk).update(status=Project.Status.ARCHIVED)
        with self.assertRaises(ValidationError):
            assign_team_member(actor=self.owner, project_id=self.project.pk, member_id=member.pk, role="member")
        self.assertEqual(PulseProjectTeamMember.objects.count(), 0)

    def test_only_post_can_change_assignments(self):
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(self._assign_url()).status_code, 405)
        self.assertEqual(PulseProjectTeamMember.objects.count(), 0)
