from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.inventory.models import Supplier as InventorySupplier
from apps.sourcing.models import SourcingMaterial, SourcingVendor, SourcingVendorOffer, SourcingVendorOfferRevision


class VendorVerificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Vendor Verify Co", slug="vendor-verify-co")
        self.other_company = Company.objects.create(name="Other Vendor Verify Co", slug="other-vendor-verify-co")
        self.owner_user = User.objects.create_user(username="verify-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.material = SourcingMaterial.objects.create(
            company=self.company,
            code="MAT-VERIFY",
            name="Verification Material",
            default_unit="ton",
        )
        self.vendor = SourcingVendor.objects.create(
            company=self.company,
            code="VND-VERIFY",
            name="Verification Vendor",
            display_name="Verification Vendor",
            primary_contact_name="Mohammed Sales",
            city="Dammam",
        )
        self.offer = SourcingVendorOffer.objects.create(
            company=self.company,
            vendor=self.vendor,
            material=self.material,
            specification="12 mm",
            available_quantity="10",
            unit="ton",
            availability="available",
            rate="2000",
            currency="SAR",
            lead_time="2 days",
            last_verified_at=timezone.now() - timedelta(days=45),
            verified_by=self.owner_user,
        )

    def _member(self, *, username: str, permissions: tuple[str, ...]):
        User = get_user_model()
        user = User.objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(
            company=self.company,
            key=f"profile-{username}",
            name=f"{username} profile",
            is_system=False,
            is_active=True,
        )
        AccessProfilePermission.objects.bulk_create(
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        )
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.CUSTOM,
            access_profile=profile,
        )
        return user, membership

    def test_editor_can_quick_verify_and_preserve_immutable_before_after(self):
        editor, _ = self._member(
            username="verify-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        response = self.client.post(
            reverse("sourcing:vendor_offer_verify", args=[self.vendor.pk, self.offer.pk]),
            {
                "availability": "limited",
                "available_quantity": "35",
                "unit": "ton",
                "minimum_quantity": "5",
                "rate": "2180",
                "currency": "SAR",
                "rate_valid_until": (timezone.localdate() + timedelta(days=7)).isoformat(),
                "lead_time": "1 day",
                "contact_name": "Mohammed Sales",
                "verification_note": "35 tons confirmed; quote valid for one week.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.offer.refresh_from_db()
        self.vendor.refresh_from_db()
        self.assertEqual(str(self.offer.available_quantity), "35.000")
        self.assertEqual(str(self.offer.rate), "2180.0000")
        self.assertEqual(self.offer.availability, "limited")
        self.assertEqual(self.offer.lead_time, "1 day")
        self.assertEqual(self.offer.verified_by_id, editor.pk)
        self.assertIsNotNone(self.offer.last_verified_at)
        self.assertIsNotNone(self.vendor.last_verified_at)

        revision = SourcingVendorOfferRevision.objects.get(offer_id_snapshot=self.offer.pk)
        self.assertEqual(revision.contact_name, "Mohammed Sales")
        self.assertEqual(revision.before["availableQuantity"], "10.000")
        self.assertEqual(revision.after["availableQuantity"], "35.000")
        self.assertEqual(revision.before["rate"], "2000.0000")
        self.assertEqual(revision.after["rate"], "2180.0000")
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                area=AuditArea.SOURCING,
                action="sourcing.vendor_offer.verified",
                object_id=self.offer.pk,
            ).exists()
        )
        self.assertEqual(InventorySupplier.objects.filter(company=self.company).count(), 0)
        with self.assertRaises(ValidationError):
            revision.delete()

    def test_viewer_can_read_history_but_cannot_verify(self):
        viewer, _ = self._member(
            username="verify-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        SourcingVendorOfferRevision.objects.create(
            company=self.company,
            offer=self.offer,
            offer_id_snapshot=self.offer.pk,
            vendor_id_snapshot=self.vendor.pk,
            material_id_snapshot=self.material.pk,
            before={"rate": "1900.0000"},
            after={"rate": "2000.0000"},
            verified_at=timezone.now(),
            actor=self.owner_user,
            contact_name="Vendor Contact",
            note="Confirmed by phone",
        )
        self.client.force_login(viewer)
        history = self.client.get(reverse("sourcing:vendor_offer_history", args=[self.vendor.pk, self.offer.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Verification History")
        self.assertContains(history, "Vendor Contact")
        self.assertContains(history, "1900.0000")
        self.assertNotContains(history, "Save Verification")
        self.assertEqual(
            self.client.get(reverse("sourcing:vendor_offer_verify", args=[self.vendor.pk, self.offer.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("sourcing:vendor_offer_verify", args=[self.vendor.pk, self.offer.pk]), {}).status_code,
            403,
        )

    def test_material_finder_links_to_history_and_editor_verification(self):
        editor, _ = self._member(
            username="verify-finder-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        response = self.client.get(reverse("sourcing:material_finder"), {"q": "Verification Material"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("sourcing:vendor_offer_history", args=[self.vendor.pk, self.offer.pk]))
        self.assertContains(response, reverse("sourcing:vendor_offer_verify", args=[self.vendor.pk, self.offer.pk]))
        self.assertContains(response, "Verify now")

    def test_quick_verification_makes_stale_offer_fresh(self):
        self.client.force_login(self.owner_user)
        before = self.client.get(reverse("sourcing:material_finder"), {"freshness": "stale"})
        self.assertEqual(before.context["page_obj"].paginator.count, 1)
        response = self.client.post(
            reverse("sourcing:vendor_offer_verify", args=[self.vendor.pk, self.offer.pk]),
            {
                "availability": "available",
                "available_quantity": "10",
                "unit": "ton",
                "minimum_quantity": "",
                "rate": "2000",
                "currency": "SAR",
                "rate_valid_until": "",
                "lead_time": "2 days",
                "contact_name": "Mohammed Sales",
                "verification_note": "Still available at the same rate.",
            },
        )
        self.assertEqual(response.status_code, 302)
        fresh = self.client.get(reverse("sourcing:material_finder"), {"freshness": "fresh"})
        self.assertEqual(fresh.context["page_obj"].paginator.count, 1)

    def test_cross_company_offer_history_and_verification_fail_closed(self):
        other_material = SourcingMaterial.objects.create(company=self.other_company, code="MAT-OTHER", name="Other Material")
        other_vendor = SourcingVendor.objects.create(company=self.other_company, code="VND-OTHER", name="Other Vendor")
        other_offer = SourcingVendorOffer.objects.create(
            company=self.other_company,
            vendor=other_vendor,
            material=other_material,
        )
        self.client.force_login(self.owner_user)
        self.assertEqual(
            self.client.get(reverse("sourcing:vendor_offer_history", args=[other_vendor.pk, other_offer.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("sourcing:vendor_offer_verify", args=[other_vendor.pk, other_offer.pk])).status_code,
            404,
        )
