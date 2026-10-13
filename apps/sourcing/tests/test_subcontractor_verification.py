"""Upgrade 06: company verification, independent freshness, immutable history, access."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import NotSupportedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import (
    SourcingService, SourcingSubcontractor, SourcingSubcontractorService,
    SourcingSubcontractorServiceRevision, SourcingSubcontractorVerificationRevision,
)
from apps.sourcing.services.subcontractor_catalog import verify_service_offer
from apps.sourcing.services.subcontractors import update_subcontractor
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class SubcontractorVerificationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Subco Verification A", slug="subco-verification-a")
        self.remote = Company.objects.create(name="Subco Verification B", slug="subco-verification-b")
        self.owner = get_user_model().objects.create_user(username="subco-verify-owner", password="test-secure-password")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.sub = SourcingSubcontractor.objects.create(
            company=self.company, code="SUB-VERIFY", name="HVAC Company", cr_number="CR-99", city="Dammam"
        )
        self.remote_sub = SourcingSubcontractor.objects.create(
            company=self.remote, code="SUB-VERIFY", name="Remote Company"
        )
        self.client.force_login(self.owner)

    def _verify(self, **overrides):
        values = {"contact_name": "Khalid", "note": "Confirmed registration and primary company contact", "confirmed": "on"}
        values.update(overrides)
        return self.client.post(reverse("sourcing:subcontractor_verify", args=[self.sub.pk]), values)

    def _member(self, suffix, grants):
        user = get_user_model().objects.create_user(username="subco-verify-" + suffix, password="test-secure-password")
        profile = AccessProfile.objects.create(company=self.company, key="subco-verify-" + suffix, name="Subco " + suffix, is_active=True)
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=grant) for grant in grants
        ])
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_confirm_company_creates_immutable_evidence_and_audit(self):
        self.assertEqual(self._verify().status_code, 302)
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.last_verified_at)
        revision = SourcingSubcontractorVerificationRevision.objects.get(company=self.company)
        self.assertEqual(revision.contact_name, "Khalid")
        self.assertEqual(revision.after["cr_number"], "CR-99")
        self.assertIsNone(revision.before["last_verified_at"])
        self.assertIsNotNone(revision.after["last_verified_at"])
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING,
            action="sourcing.subcontractor.company_verified", object_id=self.sub.pk).exists())
        self.assertContains(self.client.get(reverse("sourcing:subcontractor_verification_history", args=[self.sub.pk])), "Confirmed registration")
        with self.assertRaises(NotSupportedError):
            SourcingSubcontractorVerificationRevision.objects.filter(pk=revision.pk).update(note="Forged")
        with self.assertRaises(ValidationError):
            revision.note = "Forged"
            revision.save()
        with self.assertRaises(ValidationError):
            revision.delete()

    def test_validation_rejects_unconfirmed_missing_contacts_and_get_writes(self):
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verify", args=[self.sub.pk])).status_code, 200)
        self.assertEqual(SourcingSubcontractorVerificationRevision.objects.count(), 0)
        self.assertEqual(self._verify(confirmed="").status_code, 400)
        self.assertEqual(self._verify(note="").status_code, 400)
        self.assertEqual(self._verify(contact_name="").status_code, 400)
        self.assertIsNone(SourcingSubcontractor.objects.get(pk=self.sub.pk).last_verified_at)

    def test_company_verification_independent_of_service_offer_confirmation(self):
        service = SourcingService.objects.create(company=self.company, code="S-VER", name="Inspection")
        offer = SourcingSubcontractorService.objects.create(company=self.company, subcontractor=self.sub, service=service)
        verify_service_offer(actor_membership=self.membership, subcontractor_id=self.sub.pk, offer_id=offer.pk,
            cleaned_data={"availability": "available", "verification_note": "Offered tomorrow"}, contact_name="Supplier")
        self.sub.refresh_from_db()
        offer.refresh_from_db()
        self.assertIsNone(self.sub.last_verified_at)
        self.assertIsNotNone(offer.last_verified_at)
        self.assertEqual(SourcingSubcontractorServiceRevision.objects.count(), 1)
        self.assertEqual(SourcingSubcontractorVerificationRevision.objects.count(), 0)
        self._verify()
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.last_verified_at)
        self.assertEqual(SourcingSubcontractorVerificationRevision.objects.count(), 1)
        self.assertEqual(SourcingSubcontractorServiceRevision.objects.count(), 1)

    def test_profile_edit_invalidates_company_freshness_but_retains_evidence(self):
        self._verify()
        self.sub.refresh_from_db()
        original = self.sub.last_verified_at
        # Notes-only edits preserve a legitimately verified company identity.
        data = {key: getattr(self.sub, key) for key in ("code", "name", "display_name", "primary_contact_name",
            "company_phone", "company_email", "mobile", "email", "address", "street_number", "district",
            "city", "region", "postal_code", "service_coverage", "cr_number", "vat_number", "website", "notes")}
        update_subcontractor(actor_membership=self.membership, subcontractor_id=self.sub.pk, cleaned_data={**data, "notes": "Notes only"})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.last_verified_at, original)
        update_subcontractor(actor_membership=self.membership, subcontractor_id=self.sub.pk, cleaned_data={**data, "city": "Khobar"})
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.last_verified_at)
        self.assertEqual(SourcingSubcontractorVerificationRevision.objects.count(), 1)
        self.assertContains(self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk])), "Never verified")

    def test_stale_company_label(self):
        self.sub.last_verified_at = timezone.now() - timedelta(days=32)
        self.sub.save(update_fields=["last_verified_at"])
        response = self.client.get(reverse("sourcing:subcontractor_detail", args=[self.sub.pk]))
        self.assertContains(response, "Stale")
        self.assertContains(self.client.get(reverse("sourcing:subcontractor_list")), "Stale")

    def test_permission_boundaries_and_other_company_404(self):
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verify", args=[self.remote_sub.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_verify", args=[self.remote_sub.pk]),
            {"contact_name": "X", "note": "Y", "confirmed": "on"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verification_history", args=[self.remote_sub.pk])).status_code, 404)
        viewer = self._member("viewer", [AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value])
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verification_history", args=[self.sub.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verify", args=[self.sub.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("sourcing:subcontractor_verify", args=[self.sub.pk]),
            {"contact_name": "X", "note": "Y", "confirmed": "on"}).status_code, 403)
        self.client.force_login(self._member("vendor", [AccessPermission.SOURCING_VENDORS_VIEW.value]))
        self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verification_history", args=[self.sub.pk])).status_code, 403)

    def test_inactive_archived_trashed_cannot_verify(self):
        for field, value in (("status", "inactive"), ("archived_at", timezone.now()), ("deleted_at", timezone.now())):
            obj = SourcingSubcontractor.objects.get(pk=self.sub.pk)
            setattr(obj, field, value)
            if field == "deleted_at":
                obj.purge_after = timezone.now() + timedelta(days=30)
            obj.save()
            self.assertEqual(self.client.get(reverse("sourcing:subcontractor_verify", args=[self.sub.pk])).status_code, 403)
            self.assertEqual(self._verify().status_code, 403)
            setattr(obj, field, None if field != "status" else "active")
            if field == "deleted_at":
                obj.purge_after = None
            obj.save()
        self.assertEqual(SourcingSubcontractorVerificationRevision.objects.count(), 0)

    def test_permanent_delete_retains_detached_verification_snapshots(self):
        self._verify()
        revision = SourcingSubcontractorVerificationRevision.objects.get(company=self.company)
        response = self.client.post(reverse("sourcing:subcontractor_delete", args=[self.sub.pk]),
            {"confirmation": self.sub.code, "reason": "Retired"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SourcingSubcontractor.objects.filter(pk=self.sub.pk).exists())
        revision.refresh_from_db()
        self.assertIsNone(revision.subcontractor_id)
        self.assertEqual(revision.subcontractor_id_snapshot, self.sub.pk)
        self.assertEqual(revision.after["name"], "HVAC Company")

    def test_cross_company_revision_rejected(self):
        with self.assertRaises(ValidationError):
            SourcingSubcontractorVerificationRevision.objects.create(
                company=self.company, subcontractor=self.remote_sub, subcontractor_id_snapshot=self.remote_sub.pk,
                verified_at=timezone.now(), contact_name="Remote", note="No", actor=self.owner)
