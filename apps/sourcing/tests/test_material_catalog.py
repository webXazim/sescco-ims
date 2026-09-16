from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.inventory.models import Supplier as InventorySupplier
from apps.sourcing.models import (
    SourcingMaterial,
    SourcingVendor,
    SourcingVendorOffer,
    SourcingVendorOfferRevision,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class MaterialCatalogTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Sourcing Catalog Co", slug="sourcing-catalog-co")
        self.other_company = Company.objects.create(name="Other Sourcing Co", slug="other-sourcing-co")
        self.owner_user = User.objects.create_user(username="catalog-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.vendor = SourcingVendor.objects.create(company=self.company, code="VND-100", name="Catalog Vendor")
        self.material = SourcingMaterial.objects.create(
            company=self.company,
            code="MAT-REB12",
            name="Rebar 12mm",
            category="Civil",
            default_unit="ton",
            aliases=["Steel Bar 12mm", "Reinforcement Bar 12mm"],
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

    def test_material_master_view_and_edit_are_independent(self):
        viewer, _ = self._member(
            username="material-viewer",
            permissions=(AccessPermission.SOURCING_MASTERS_VIEW.value,),
        )
        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:material_list"), {"q": "reinforcement bar"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rebar 12mm")
        self.assertEqual(self.client.get(reverse("sourcing:material_create")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("sourcing:material_status", args=[self.material.pk]), {"active": "0"}).status_code,
            403,
        )

    def test_material_manager_creates_aliases_and_rejects_alias_collision(self):
        manager, _ = self._member(
            username="material-manager",
            permissions=(
                AccessPermission.SOURCING_MASTERS_VIEW.value,
                AccessPermission.SOURCING_MASTERS_MANAGE.value,
            ),
        )
        self.client.force_login(manager)
        response = self.client.post(
            reverse("sourcing:material_create"),
            {
                "code": "MAT-CBL",
                "name": "Electrical Cable",
                "category": "Electrical",
                "default_unit": "m",
                "aliases": "Power Cable\nLV Cable",
                "notes": "Sourcing reference only",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = SourcingMaterial.objects.get(company=self.company, code="MAT-CBL")
        self.assertEqual(created.aliases, ["Power Cable", "LV Cable"])
        self.assertIn("power cable", created.normalized_aliases)

        collision = self.client.post(
            reverse("sourcing:material_create"),
            {
                "code": "MAT-CBL-2",
                "name": "Different Cable",
                "category": "Electrical",
                "default_unit": "m",
                "aliases": "Power Cable",
                "notes": "",
            },
        )
        self.assertEqual(collision.status_code, 400)
        self.assertFalse(SourcingMaterial.objects.filter(company=self.company, code="MAT-CBL-2").exists())

    def test_vendor_editor_adds_reference_offer_and_revision_without_inventory_supplier(self):
        editor, _ = self._member(
            username="vendor-catalog-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        before_inventory_suppliers = InventorySupplier.objects.filter(company=self.company).count()
        self.client.force_login(editor)
        response = self.client.post(
            reverse("sourcing:vendor_offer_create", args=[self.vendor.pk]),
            {
                "material": str(self.material.pk),
                "specification": "Grade 60",
                "brand": "Reference Brand",
                "model": "",
                "available_quantity": "25.500",
                "unit": "ton",
                "minimum_quantity": "5",
                "availability": "available",
                "rate": "2180.0000",
                "currency": "SAR",
                "rate_valid_until": "2030-12-31",
                "lead_time": "1 day",
                "verification_note": "Confirmed by phone",
                "notes": "Call before order",
                "verified_now": "on",
                "contact_name": "Mohammed",
            },
        )
        self.assertEqual(response.status_code, 302)
        offer = SourcingVendorOffer.objects.get(company=self.company, vendor=self.vendor, material=self.material)
        self.assertEqual(str(offer.available_quantity), "25.500")
        self.assertEqual(str(offer.rate), "2180.0000")
        self.assertIsNotNone(offer.last_verified_at)
        self.assertEqual(offer.verified_by, editor)
        self.assertEqual(InventorySupplier.objects.filter(company=self.company).count(), before_inventory_suppliers)
        revision = SourcingVendorOfferRevision.objects.get(company=self.company, offer_id_snapshot=offer.pk)
        self.assertEqual(revision.contact_name, "Mohammed")
        self.assertEqual(revision.after["materialCode"], "MAT-REB12")
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                area=AuditArea.SOURCING,
                action="sourcing.vendor_offer.created",
                object_id=str(offer.pk),
            ).exists()
        )

    def test_vendor_viewer_sees_catalog_but_cannot_mutate(self):
        viewer, _ = self._member(
            username="catalog-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        offer = SourcingVendorOffer.objects.create(
            company=self.company,
            vendor=self.vendor,
            material=self.material,
            availability="limited",
            available_quantity="8",
            rate="2200",
            currency="SAR",
            unit="ton",
        )
        self.client.force_login(viewer)
        detail = self.client.get(reverse("sourcing:vendor_detail", args=[self.vendor.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Rebar 12mm")
        self.assertEqual(self.client.get(reverse("sourcing:vendor_offer_create", args=[self.vendor.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("sourcing:vendor_offer_status", args=[self.vendor.pk, offer.pk]),
                {"active": "0"},
            ).status_code,
            403,
        )

    def test_cross_company_material_cannot_be_assigned_to_vendor_offer(self):
        editor, _ = self._member(
            username="vendor-cross-company-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        foreign = SourcingMaterial.objects.create(
            company=self.other_company,
            code="MAT-FOREIGN",
            name="Foreign Material",
            default_unit="pcs",
        )
        self.client.force_login(editor)
        response = self.client.post(
            reverse("sourcing:vendor_offer_create", args=[self.vendor.pk]),
            {
                "material": str(foreign.pk),
                "specification": "",
                "brand": "",
                "model": "",
                "available_quantity": "1",
                "unit": "pcs",
                "minimum_quantity": "",
                "availability": "available",
                "rate": "1",
                "currency": "SAR",
                "rate_valid_until": "",
                "lead_time": "",
                "verification_note": "",
                "notes": "",
                "verified_now": "on",
                "contact_name": "",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingVendorOffer.objects.filter(company=self.company, material=foreign).exists())

    def test_material_deactivation_preserves_existing_offer(self):
        manager, _ = self._member(
            username="material-state-manager",
            permissions=(
                AccessPermission.SOURCING_MASTERS_VIEW.value,
                AccessPermission.SOURCING_MASTERS_MANAGE.value,
            ),
        )
        offer = SourcingVendorOffer.objects.create(
            company=self.company,
            vendor=self.vendor,
            material=self.material,
            availability="unknown",
        )
        self.client.force_login(manager)
        response = self.client.post(reverse("sourcing:material_status", args=[self.material.pk]), {"active": "0"})
        self.assertEqual(response.status_code, 302)
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_active)
        self.assertTrue(SourcingVendorOffer.objects.filter(pk=offer.pk).exists())
