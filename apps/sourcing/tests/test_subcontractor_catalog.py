"""Upgrade 04: Service Catalog CRUD, isolation, immutable verification and lifecycle regressions."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import (
    SourcingService, SourcingSubcontractor, SourcingSubcontractorService,
    SourcingSubcontractorServiceRevision,
)
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class SubcontractorCatalogTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Service Catalog A", slug="service-catalog-a")
        self.other_company = Company.objects.create(name="Service Catalog B", slug="service-catalog-b")
        self.owner = get_user_model().objects.create_user(username="service-catalog-owner", password="test-secure-password")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.sub = SourcingSubcontractor.objects.create(company=self.company, code="SUB-CAT-01", name="Mechanical Services")
        self.service = SourcingService.objects.create(company=self.company, code="SRV-HVAC", name="HVAC Installation")
        self.remote_sub = SourcingSubcontractor.objects.create(company=self.other_company, code="SUB-CAT-01", name="Remote Provider")
        self.remote_service = SourcingService.objects.create(company=self.other_company, code="SRV-R", name="Remote Service")
        self.client.force_login(self.owner)

    def _create(self, **data):
        values = {"service": str(self.service.pk), "scope_description": "Chiller installation",
                  "service_location": "Dammam", "availability": "available", "rate": "250.0000",
                  "currency": "SAR", "rate_basis": "day", "lead_time": "2 weeks"}
        values.update(data)
        return self.client.post(reverse("sourcing:subcontractor_service_create", args=[self.sub.pk]), values)

    def _viewer(self):
        user = get_user_model().objects.create_user(username="service-catalog-viewer", password="test-secure-password")
        profile = AccessProfile.objects.create(company=self.company, key="service-catalog-viewer", name="Viewer", is_active=True)
        AccessProfilePermission.objects.create(profile=profile, permission=AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value)
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_create_catalog_and_profile_renders_with_no_unrelated_mutations(self):
        self.assertEqual(self._create().status_code, 302)
        offer = SourcingSubcontractorService.objects.get(company=self.company, subcontractor=self.sub)
        self.assertEqual(offer.rate, Decimal("250.0000"))
        self.assertIsNone(offer.last_verified_at)
        self.assertEqual(SourcingSubcontractorServiceRevision.objects.count(), 0)
        response = self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk]))
        self.assertContains(response, "HVAC Installation")
        self.assertContains(response, "Chiller installation")
        self.assertContains(response, "250.0000")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING,
                        object_id=offer.pk, action="sourcing.subcontractor_service.created").exists())
        self.assertContains(response, "sourcing.subcontractor_service.created")

    def test_scoped_choices_and_cross_tenant_record_ids(self):
        create_url = reverse("sourcing:subcontractor_service_create", args=[self.sub.pk])
        response = self.client.get(create_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Remote Service")
        self.assertEqual(self._create(service=str(self.remote_service.pk)).status_code, 400)
        self.assertEqual(SourcingSubcontractorService.objects.filter(company=self.company).count(), 0)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_create", args=[self.remote_sub.pk])).status_code, 404)
        remote_offer = SourcingSubcontractorService.objects.create(company=self.other_company,
            subcontractor=self.remote_sub, service=self.remote_service)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_edit", args=[self.sub.pk, remote_offer.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_service_delete", args=[self.sub.pk, remote_offer.pk]), {"confirmation": "SRV-R"}).status_code, 404)

    def test_role_and_http_method_guards(self):
        self._create()
        offer = SourcingSubcontractorService.objects.get(company=self.company)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_delete", args=[self.sub.pk, offer.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_status", args=[self.sub.pk, offer.pk])).status_code, 403)
        self.client.force_login(self._viewer())
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk])).status_code, 200)
        self.assertNotContains(self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk])), "Add Service")
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_history", args=[self.sub.pk, offer.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_edit", args=[self.sub.pk, offer.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_service_status", args=[self.sub.pk, offer.pk]), {"active": "0"}).status_code, 403)

    def test_verification_history_and_unverified_edit_invalidates_freshness(self):
        self._create(verified_now="on", contact_name="Operations Manager", verification_note="Confirmed by telephone")
        offer = SourcingSubcontractorService.objects.get(company=self.company)
        self.assertIsNotNone(offer.last_verified_at)
        self.assertEqual(SourcingSubcontractorServiceRevision.objects.filter(offer=offer).count(), 1)
        verify_url = reverse("sourcing:subcontractor_service_verify", args=[self.sub.pk, offer.pk])
        response = self.client.post(verify_url, {"availability": "limited", "rate": "300",
            "currency": "SAR", "rate_basis": "day", "lead_time": "3 weeks",
            "contact_name": "Service Contact", "verification_note": "Renewed quote"})
        self.assertEqual(response.status_code, 302)
        offer.refresh_from_db()
        self.assertEqual(offer.rate, Decimal("300"))
        revisions = SourcingSubcontractorServiceRevision.objects.filter(offer=offer)
        self.assertEqual(revisions.count(), 2)
        self.assertEqual(revisions.order_by("-verified_at").first().contact_name, "Service Contact")
        self.assertContains(self.client.get(reverse("sourcing:subcontractor_service_history", args=[self.sub.pk, offer.pk])), "Renewed quote")
        edit_url = reverse("sourcing:subcontractor_service_edit", args=[self.sub.pk, offer.pk])
        response = self.client.post(edit_url, {"service": str(self.service.pk), "scope_description": "Chiller installation",
            "service_location": "Riyadh", "availability": "limited", "rate": "300",
            "currency": "SAR", "rate_basis": "day", "lead_time": "3 weeks"})
        self.assertEqual(response.status_code, 302)
        offer.refresh_from_db()
        self.assertIsNone(offer.last_verified_at)
        self.assertEqual(revisions.count(), 2)

    def test_lifecycle_deletion_confirmation_and_evidence_retention(self):
        self._create(verified_now="on", verification_note="Confirmed")
        offer = SourcingSubcontractorService.objects.get(company=self.company)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_service_delete", args=[self.sub.pk, offer.pk]),
                             {"confirmation": "wrong"}).status_code, 302)
        self.assertTrue(SourcingSubcontractorService.objects.filter(pk=offer.pk).exists())
        status_url = reverse("sourcing:subcontractor_service_status", args=[self.sub.pk, offer.pk])
        self.client.post(status_url, {"active": "0"})
        offer.refresh_from_db()
        self.assertFalse(offer.is_active)
        self.client.post(status_url, {"active": "1"})
        offer.refresh_from_db()
        self.assertTrue(offer.is_active)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_service_delete", args=[self.sub.pk, offer.pk]),
                             {"confirmation": "SRV-HVAC"}).status_code, 302)
        self.assertFalse(SourcingSubcontractorService.objects.filter(pk=offer.pk).exists())
        evidence = SourcingSubcontractorServiceRevision.objects.get(offer_id_snapshot=offer.pk)
        self.assertIsNone(evidence.offer_id)
        self.assertEqual(evidence.after["serviceName"], "HVAC Installation")
        with self.assertRaises(ValidationError):
            evidence.save()

    def test_archived_profile_and_inactive_master_rejected(self):
        self.service.is_active = False
        self.service.save()
        self.assertEqual(self._create().status_code, 400)
        self.service.is_active = True
        self.service.save()
        self.sub.archived_at = timezone.now()
        self.sub.save()
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_service_create", args=[self.sub.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_service_create", args=[self.sub.pk]), {"service": str(self.service.pk)}).status_code, 404)

    def test_duplicate_service_scope_rejected(self):
        self._create()
        self.assertEqual(self._create().status_code, 400)
        self.assertEqual(SourcingSubcontractorService.objects.filter(company=self.company).count(), 1)
        self.assertEqual(self._create(scope_description="chiller installation", service_location="dammam").status_code, 400)
        self.assertEqual(self._create(scope_description="Preventive Maintenance").status_code, 302)
        self.assertEqual(SourcingSubcontractorService.objects.filter(company=self.company).count(), 2)
