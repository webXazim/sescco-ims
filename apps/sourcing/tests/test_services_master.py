"""Upgrade 02: company-isolated Services master and permissions regression tests."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import SourcingService, SourcingSubcontractor, SourcingSubcontractorService
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ServicesMasterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Service Directory", slug="services-directory-one")
        self.other = Company.objects.create(name="Other Service Directory", slug="services-directory-two")
        self.owner_user = User.objects.create_user(username="services-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.service = SourcingService.objects.create(
            company=self.company, code="SRV-100", name="Equipment Calibration",
            category="Testing", aliases=["Calibrating Equipment"], default_rate_basis="visit",
        )
        self.remote = SourcingService.objects.create(
            company=self.other, code="SRV-100", name="Remote Service", category="Confidential",
        )

    def _member(self, username, permissions):
        user = get_user_model().objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(
            company=self.company, key=f"test-{username}", name=f"{username} profile",
            is_system=False, is_active=True,
        )
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        ])
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_viewer_sees_only_company_and_cannot_mutate(self):
        user = self._member("services-viewer", (AccessPermission.SOURCING_MASTERS_VIEW.value,))
        self.client.force_login(user)
        response = self.client.get(reverse("sourcing:service_list"), {"status": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipment Calibration")
        self.assertNotContains(response, "Remote Service")
        self.assertNotContains(response, "Confidential")
        self.assertEqual(self.client.get(reverse("sourcing:service_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sourcing:service_edit", args=[self.service.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("sourcing:service_status", args=[self.service.pk]), {"active": "0"}).status_code, 403)

    def test_actions_require_manage_and_post(self):
        user = self._member("services-manager", (
            AccessPermission.SOURCING_MASTERS_VIEW.value,
            AccessPermission.SOURCING_MASTERS_MANAGE.value,
        ))
        self.client.force_login(user)
        for name in ("service_status", "service_delete"):
            self.assertEqual(self.client.get(reverse(f"sourcing:{name}", args=[self.service.pk])).status_code, 403)

    def test_owner_creates_reuses_category_and_audits(self):
        self.client.force_login(self.owner_user)
        response = self.client.post(reverse("sourcing:service_create"), {
            "code": "SRV-HVAC", "name": "HVAC Installation", "category": "__new__",
            "new_category": "Mechanical Services", "default_rate_basis": "job",
            "aliases": "Air Conditioning Installation\nAC Installation\nac installation",
            "description": "Installation and commissioning", "notes": "Internal only",
        })
        self.assertRedirects(response, reverse("sourcing:service_list"))
        service = SourcingService.objects.get(company=self.company, code="SRV-HVAC")
        self.assertEqual(service.category, "Mechanical Services")
        self.assertEqual(service.aliases, ["Air Conditioning Installation", "AC Installation"])
        self.assertTrue(AuditEvent.objects.filter(
            company=self.company, area=AuditArea.SOURCING, object_id=service.pk,
            action="sourcing.service.created",
        ).exists())
        edit_page = self.client.get(reverse("sourcing:service_edit", args=[service.pk]))
        self.assertContains(edit_page, "Mechanical Services")

    def test_alias_collision_and_duplicate_normalized_name(self):
        self.client.force_login(self.owner_user)
        for name, alias in (("Calibrating Equipment", ""), ("HVAC Support", "calibrating equipment")):
            response = self.client.post(reverse("sourcing:service_create"), {
                "code": f"SRV-BAD-{len(name)}", "name": name,
                "category": "Testing", "new_category": "", "default_rate_basis": "",
                "aliases": alias, "description": "", "notes": "",
            })
            self.assertEqual(response.status_code, 400)
            self.assertFalse(SourcingService.objects.filter(company=self.company, name=name).exists())

    def test_normalized_service_name_conflicts_are_rejected(self):
        self.client.force_login(self.owner_user)
        response = self.client.post(reverse("sourcing:service_create"), {
            "code": "SRV-DUP", "name": "  equipment   calibration ", "category": "Testing",
            "new_category": "", "default_rate_basis": "", "aliases": "", "description": "", "notes": "",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingService.objects.filter(company=self.company, code="SRV-DUP").exists())

    def test_status_lifecycle_and_company_boundary(self):
        self.client.force_login(self.owner_user)
        status = reverse("sourcing:service_status", args=[self.service.pk])
        self.assertRedirects(self.client.post(status, {"active": "0"}), reverse("sourcing:service_list"))
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.assertEqual(self.client.get(reverse("sourcing:service_list")).status_code, 200)
        self.assertRedirects(self.client.post(status, {"active": "1"}), reverse("sourcing:service_list"))
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)
        self.assertEqual(self.client.get(reverse("sourcing:service_edit", args=[self.remote.pk])).status_code, 404)
        # Forbidden cross-tenant POST cannot alter a foreign service.
        self.assertRedirects(self.client.post(reverse("sourcing:service_status", args=[self.remote.pk]), {"active": "0"}), reverse("sourcing:service_list"))
        self.remote.refresh_from_db()
        self.assertTrue(self.remote.is_active)

    def test_delete_requires_confirmation_and_disallows_referenced_services(self):
        self.client.force_login(self.owner_user)
        url = reverse("sourcing:service_delete", args=[self.service.pk])
        self.assertRedirects(self.client.post(url, {"confirmation": "WRONG"}), reverse("sourcing:service_list"))
        self.assertTrue(SourcingService.objects.filter(pk=self.service.pk).exists())
        subco = SourcingSubcontractor.objects.create(company=self.company, code="SC-01", name="Calibration Contractor")
        SourcingSubcontractorService.objects.create(company=self.company, subcontractor=subco, service=self.service)
        self.assertRedirects(self.client.post(url, {"confirmation": self.service.code}), reverse("sourcing:service_list"))
        self.assertTrue(SourcingService.objects.filter(pk=self.service.pk).exists())
        unreferenced = SourcingService.objects.create(company=self.company, code="SRV-DELETE", name="Temporary Service")
        self.assertRedirects(self.client.post(reverse("sourcing:service_delete", args=[unreferenced.pk]), {
            "confirmation": "SRV-DELETE"
        }), reverse("sourcing:service_list"))
        self.assertFalse(SourcingService.objects.filter(pk=unreferenced.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(object_id=unreferenced.pk, action="sourcing.service.deleted").exists())

    def test_navigation_is_permission_scoped(self):
        viewer = self._member("services-nav", (AccessPermission.SOURCING_MASTERS_VIEW.value,))
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:home"))
        self.assertContains(response, reverse("sourcing:service_list"))
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse("sourcing:service_list")).status_code, 200)
