"""Upgrade 03: independent Subcontractor Directory HTTP and lifecycle regressions."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import SourcingSubcontractor, SourcingSubcontractorContact, SourcingService, SourcingSubcontractorService
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class SubcontractorDirectoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Subco Directory One", slug="subco-dir-one")
        self.remote = Company.objects.create(name="Subco Directory Two", slug="subco-dir-two")
        self.owner_user = get_user_model().objects.create_user(username="subco-owner", password="test-secure-password")
        CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.obj = SourcingSubcontractor.objects.create(company=self.company, code="SUB-001", name="HVAC Specialists", city="Dammam")
        self.other = SourcingSubcontractor.objects.create(company=self.remote, code="SUB-001", name="Remote Confidential")

    def _member(self, username, permissions):
        user = get_user_model().objects.create_user(username=username, password="test-secure-password")
        profile = AccessProfile.objects.create(company=self.company, key="test-" + username, name="Test " + username, is_system=False, is_active=True)
        AccessProfilePermission.objects.bulk_create([AccessProfilePermission(profile=profile, permission=permission) for permission in permissions])
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_owner_browses_and_edits_company_scoped_directory(self):
        self.client.force_login(self.owner_user)
        response = self.client.get(reverse("sourcing:subcontractor_list"), {"q": "HVAC"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HVAC Specialists")
        self.assertNotContains(response, "Remote Confidential")
        self.assertContains(response, reverse("sourcing:subcontractor_create"))
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_detail", args=[self.other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_edit", args=[self.other.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_status", args=[self.other.pk]), {"status": "inactive"}).status_code, 404)
        self.other.refresh_from_db()
        self.assertEqual(self.other.status, "active")

    def test_independent_grant_prevents_vendor_and_manpower_access_bleed(self):
        vendor_only = self._member("subco-vendor-only", (AccessPermission.SOURCING_VENDORS_VIEW.value, AccessPermission.SOURCING_VENDORS_MANAGE.value))
        self.client.force_login(vendor_only)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_create"), {"name": "Injected"}).status_code, 403)
        self.client.logout()
        subco_viewer = self._member("subco-viewer", (AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value,))
        self.client.force_login(subco_viewer)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("sourcing:vendor_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_create")).status_code, 403)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_status", args=[self.obj.pk]), {"status": "inactive"}).status_code, 403)
        self.assertNotContains(self.client.get(reverse("sourcing:subcontractor_list")), reverse("sourcing:subcontractor_create"))

    def test_create_edit_and_audit(self):
        self.client.force_login(self.owner_user)
        response = self.client.post(reverse("sourcing:subcontractor_create"), {"name": "Industrial Repair Co", "city": "Khobar"})
        self.assertEqual(response.status_code, 302)
        obj = SourcingSubcontractor.objects.get(company=self.company, name="Industrial Repair Co")
        self.assertTrue(obj.code.startswith("SUB-"))
        self.assertRedirects(response, reverse("sourcing:subcontractor_detail", args=[obj.pk]))
        response = self.client.post(reverse("sourcing:subcontractor_edit", args=[obj.pk]), {"code": obj.code, "name": "Industrial Repair Co LLC", "city": "Dammam"})
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.city, "Dammam")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING, object_id=obj.pk, action="sourcing.subcontractor.updated").exists())

    def test_contact_primary_uniqueness_and_deactivation(self):
        self.client.force_login(self.owner_user)
        url = reverse("sourcing:subcontractor_contact_create", args=[self.obj.pk])
        for name in ("Ahmad", "Ali"):
            response = self.client.post(url, {"first_name": name, "email": f"{name.lower()}@example.com", "is_primary": "on", "is_active": "on"})
            self.assertEqual(response.status_code, 302)
        contacts = SourcingSubcontractorContact.objects.for_company(self.company).filter(subcontractor=self.obj)
        self.assertEqual(contacts.count(), 2)
        self.assertEqual(contacts.filter(is_primary=True, is_active=True).count(), 1)
        primary = contacts.get(is_primary=True)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.primary_contact_name, primary.full_name)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_contact_deactivate", args=[self.obj.pk, primary.pk])).status_code, 403)
        self.client.post(reverse("sourcing:subcontractor_contact_deactivate", args=[self.obj.pk, primary.pk]))
        primary.refresh_from_db()
        self.assertFalse(primary.is_active)
        self.assertFalse(primary.is_primary)

    def test_archival_trash_and_safe_permanent_delete(self):
        self.client.force_login(self.owner_user)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_archive", args=[self.obj.pk])).status_code, 403)
        self.client.post(reverse("sourcing:subcontractor_archive", args=[self.obj.pk]), {"reason": "Closed"})
        self.obj.refresh_from_db()
        self.assertIsNotNone(self.obj.archived_at)
        self.assertEqual(self.obj.status, "inactive")
        self.client.post(reverse("sourcing:subcontractor_restore_archive", args=[self.obj.pk]))
        self.client.post(reverse("sourcing:subcontractor_trash", args=[self.obj.pk]), {"confirmation": "BAD", "reason": "Duplicate"})
        self.obj.refresh_from_db()
        self.assertIsNone(self.obj.deleted_at)
        self.client.post(reverse("sourcing:subcontractor_trash", args=[self.obj.pk]), {"confirmation": "SUB-001", "reason": "Duplicate"})
        self.obj.refresh_from_db()
        self.assertIsNotNone(self.obj.deleted_at)
        self.client.post(reverse("sourcing:subcontractor_restore_trash", args=[self.obj.pk]))
        self.obj.refresh_from_db()
        self.assertIsNone(self.obj.deleted_at)
        service = SourcingService.objects.create(company=self.company, code="SRV-03", name="Equipment Cleaning")
        SourcingSubcontractorService.objects.create(company=self.company, subcontractor=self.obj, service=service)
        self.client.post(reverse("sourcing:subcontractor_delete", args=[self.obj.pk]), {"confirmation": "SUB-001", "reason": "Closed"})
        self.assertTrue(SourcingSubcontractor.objects.filter(pk=self.obj.pk).exists())
        SourcingSubcontractorService.objects.filter(subcontractor=self.obj).delete()
        self.client.post(reverse("sourcing:subcontractor_delete", args=[self.obj.pk]), {"confirmation": "SUB-001", "reason": "Closed"})
        self.assertFalse(SourcingSubcontractor.objects.filter(pk=self.obj.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(company=self.company, object_id=self.obj.pk, action="sourcing.subcontractor.deleted").exists())

    def test_directory_service_counts_are_active_and_company_scoped(self):
        """Directory summary does not leak remote or inactive service entries."""
        self.client.force_login(self.owner_user)
        active = SourcingService.objects.create(company=self.company, code="SRV-U09-01", name="Calibration")
        inactive = SourcingService.objects.create(company=self.company, code="SRV-U09-02", name="Installation", is_active=False)
        remote_service = SourcingService.objects.create(company=self.remote, code="SRV-U09-03", name="Restricted")
        SourcingSubcontractorService.objects.create(company=self.company, subcontractor=self.obj, service=active)
        SourcingSubcontractorService.objects.create(company=self.company, subcontractor=self.obj, service=inactive)
        SourcingSubcontractorService.objects.create(company=self.remote, subcontractor=self.other, service=remote_service)
        response = self.client.get(reverse("sourcing:subcontractor_list"), {"sort": "updated", "dir": "desc"})
        self.assertEqual(response.status_code, 200)
        rows = list(response.context["subcontractors"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].active_service_count, 1)
        self.assertContains(response, "subcontractor-sort")
        self.assertContains(response, "Active Services")
        self.assertNotContains(response, "Remote Confidential")

    def test_subcontractor_profile_section_navigation_respects_view_permissions(self):
        viewer = self._member("subco-u09-viewer", (AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value,))
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:subcontractor_detail", args=[self.obj.pk]))
        self.assertEqual(response.status_code, 200)
        for anchor in ("#company-information", "#service-catalog", "#qualifications", "#contacts", "#activity"):
            self.assertContains(response, 'href="' + anchor + '"')
        self.assertNotContains(response, 'href="#lifecycle"')
