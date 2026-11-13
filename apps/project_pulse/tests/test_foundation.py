"""U01 integration/security tests. Run with manage.py test apps.project_pulse."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission, permissions_for_legacy_role
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.access_profiles import _clean_permissions, permission_catalog
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership, ScopeMode
from apps.accounts.modules import PlatformModule, membership_can_module, module_from_path
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.projects.models import Project


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class ProjectPulseFoundationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Pulse Main Co", slug="pulse-main-co")
        self.other_company = Company.objects.create(name="Pulse Other Co", slug="pulse-other-co")
        self.owner_user = User.objects.create_user(username="pulse-owner", password="TestPass!2026")
        self.owner = CompanyMembership.objects.create(
            company=self.company, user=self.owner_user, role=AccessRole.OWNER
        )
        self.p1 = Project.objects.create(company=self.company, code="PUL-01", name="Civil Package", manager_name="Manager A")
        self.p2 = Project.objects.create(company=self.company, code="PUL-02", name="Electrical Package")
        self.foreign = Project.objects.create(company=self.other_company, code="PUL-99", name="Hidden Other Company")

    def _viewer(self, *, username, perms, scope=ScopeMode.ALL, assigned=()):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="TestPass!2026")
        profile = AccessProfile.objects.create(
            company=self.company, key=f"custom-{username}", name=username, is_system=False
        )
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=permission) for permission in perms
        ])
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM,
            access_profile=profile, project_scope_mode=scope,
        )
        if scope == ScopeMode.SELECTED:
            for project in assigned:
                membership.project_scopes.create(project=project)
        return user, membership

    def test_owner_has_independent_pulse_authority_after_seeding(self):
        self.assertTrue(membership_has_permission(self.owner, AccessPermission.PULSE_OVERVIEW_VIEW))
        self.assertTrue(membership_has_permission(self.owner, AccessPermission.PULSE_PROJECTS_VIEW))
        self.assertTrue(membership_can_module(self.owner, PlatformModule.PROJECT_PULSE))
        self.assertEqual(module_from_path('/app/project-pulse/projects/'), PlatformModule.PROJECT_PULSE)

    def test_default_operational_roles_do_not_inherit_pulse(self):
        for role in (AccessRole.PROJECT_MANAGER, AccessRole.INVENTORY_MANAGER,
                     AccessRole.OPERATIONS_ADMIN, AccessRole.FINANCE_MANAGER):
            with self.subTest(role=role):
                self.assertNotIn(AccessPermission.PULSE_OVERVIEW_VIEW, permissions_for_legacy_role(role))
                self.assertNotIn(AccessPermission.PULSE_PROJECTS_VIEW, permissions_for_legacy_role(role))

    def test_owner_overview_reads_existing_project_records_and_switcher(self):
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse('project_pulse:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Civil Package')
        self.assertNotContains(response, 'Hidden Other Company')
        self.assertEqual(response.context['counts']['total'], 2)
        modules = response.context['PLATFORM_CONTEXT']['modules']
        self.assertTrue(next(m['active'] for m in modules if m['key'] == 'project_pulse'))
        self.assertContains(response, 'Project Pulse')

    def test_owner_project_list_and_detail_are_read_only(self):
        self.client.force_login(self.owner_user)
        listing = self.client.get(reverse('project_pulse:project_list'), {'q': 'Civil', 'status': 'active'})
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Civil Package')
        self.assertNotContains(listing, 'Electrical Package')
        detail = self.client.get(reverse('project_pulse:project_detail', args=[self.p1.code]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Manager A')
        self.assertEqual(self.client.post(reverse('project_pulse:home')).status_code, 405)

    def test_no_authority_denies_module_even_when_user_can_use_other_modules(self):
        user, membership = self._viewer(username='inventory-only', perms=(AccessPermission.INVENTORY_STOCK_VIEW.value,))
        self.assertFalse(membership_can_module(membership, PlatformModule.PROJECT_PULSE))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('project_pulse:home')).status_code, 403)
        self.assertEqual(self.client.get(reverse('project_pulse:project_list')).status_code, 403)
        self.assertNotIn('project_pulse', [m['key'] for m in self.client.get(reverse('core:dashboard')).context['PLATFORM_CONTEXT']['modules']])

    def test_access_profiles_show_pulse_permissions_and_require_overview(self):
        pulse = [x for x in permission_catalog() if x['category'] == 'Project Pulse']
        self.assertTrue({'pulse.overview.view', 'pulse.projects.view', 'pulse.team.view',
            'pulse.team.manage', 'pulse.categories.view', 'pulse.categories.manage',
            'pulse.tasks.view', 'pulse.tasks.manage', 'pulse.progress.view',
            'pulse.progress.update'}.issubset({x['code'] for x in pulse}))
        self.assertEqual({x['code'] for x in pulse},
                         {permission.value for permission in AccessPermission if permission.value.startswith('pulse.')})
        with self.assertRaises(ValidationError):
            _clean_permissions(['pulse.projects.view'])
        self.assertEqual(set(_clean_permissions(['pulse.overview.view', 'pulse.projects.view'])),
                         {'pulse.overview.view', 'pulse.projects.view'})

    def test_project_scopes_are_enforced_at_list_detail_and_counts(self):
        user, _ = self._viewer(username='pulse-scoped', perms=('pulse.overview.view', 'pulse.projects.view'),
                               scope=ScopeMode.SELECTED, assigned=(self.p1,))
        self.client.force_login(user)
        overview = self.client.get(reverse('project_pulse:home'))
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.context['counts']['total'], 1)
        self.assertContains(overview, 'Civil Package')
        self.assertNotContains(overview, 'Electrical Package')
        listing = self.client.get(reverse('project_pulse:project_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Civil Package')
        self.assertNotContains(listing, 'Electrical Package')
        self.assertEqual(self.client.get(reverse('project_pulse:project_detail', args=[self.p2.code])).status_code, 404)
        self.assertEqual(self.client.get(reverse('project_pulse:project_detail', args=[self.foreign.code])).status_code, 404)

    def test_overview_only_does_not_open_project_directory(self):
        user, _ = self._viewer(username='pulse-overview-only', perms=('pulse.overview.view',))
        self.client.force_login(user)
        overview = self.client.get(reverse('project_pulse:home'))
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.context['counts']['total'], 2)
        self.assertEqual(list(overview.context['projects']), [])
        self.assertNotContains(overview, 'Civil Package')
        self.assertNotContains(overview, 'Electrical Package')
        self.assertNotContains(overview, 'Manager A')
        self.assertEqual(self.client.get(reverse('project_pulse:project_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('project_pulse:project_detail', args=[self.p1.code])).status_code, 403)

    def test_no_project_scope_sees_no_projects(self):
        user, _ = self._viewer(username='pulse-no-scope', perms=('pulse.overview.view', 'pulse.projects.view'),
                               scope=ScopeMode.NONE)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('project_pulse:home')).context['counts']['total'], 0)
        self.assertEqual(self.client.get(reverse('project_pulse:project_detail', args=[self.p1.code])).status_code, 404)
