from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import (
    SourcingEntityStatus,
    SourcingMaterial,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class VendorSourcingMasterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Vendor Directory Co", slug="vendor-directory-co")
        self.other_company = Company.objects.create(name="Other Vendor Co", slug="other-vendor-co")
        self.owner_user = User.objects.create_user(username="vendor-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)

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

    def test_vendor_viewer_can_search_and_paginate_but_cannot_mutate(self):
        viewer, _membership = self._member(
            username="vendor-view-only",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        for index in range(55):
            SourcingVendor.objects.create(
                company=self.company,
                code=f"VND-{index:04d}",
                name=f"Vendor {index:04d}",
                email=f"vendor{index}@example.com",
            )
        SourcingVendor.objects.create(company=self.other_company, code="VND-OTHER", name="Other Tenant Vendor")

        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:vendor_list"), {"page_size": 50, "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["vendors"]), 5)
        self.assertNotContains(response, "Other Tenant Vendor")

        search = self.client.get(reverse("sourcing:vendor_list"), {"q": "vendor17@example.com"})
        self.assertEqual(search.context["page_obj"].paginator.count, 1)
        self.assertContains(search, "Vendor 0017")

        self.assertEqual(self.client.get(reverse("sourcing:vendor_create")).status_code, 403)
        target = SourcingVendor.objects.for_company(self.company).first()
        self.assertEqual(
            self.client.post(reverse("sourcing:vendor_status", args=[target.pk]), {"status": "inactive"}).status_code,
            403,
        )

    def test_vendor_editor_creates_updates_contacts_and_audit(self):
        editor, _membership = self._member(
            username="vendor-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        create = self.client.post(
            reverse("sourcing:vendor_create"),
            {
                "code": "VND-1001",
                "name": "Eastern Material Source",
                "display_name": "Eastern Material",
                "cr_number": "CR1001",
                "vat_number": "VAT1001",
                "company_phone": "+966133000001",
                "company_email": "info@example.com",
                "website": "https://example.com",
                "primary_contact_name": "Ahmed Saleh",
                "mobile": "+966500000001",
                "email": "sales@example.com",
                "address": "King Fahd Road, Building 12",
                "street_number": "2451",
                "district": "Al Faisaliyah",
                "city": "Dammam",
                "region": "Eastern Province",
                "postal_code": "32271",
                "notes": "Reference vendor only",
            },
        )
        self.assertEqual(create.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company, code="VND-1001")
        self.assertEqual(vendor.company_phone, "+966133000001")
        self.assertEqual(vendor.company_email, "info@example.com")
        self.assertEqual(vendor.address, "King Fahd Road, Building 12")
        self.assertEqual(vendor.district, "Al Faisaliyah")
        self.assertEqual(vendor.postal_code, "32271")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING, action="sourcing.vendor.created", object_id=str(vendor.pk)).exists())

        contact = self.client.post(
            reverse("sourcing:vendor_contact_create", args=[vendor.pk]),
            {
                "salutation": "Mr",
                "first_name": "Mohammed",
                "last_name": "Ali",
                "designation": "Sales Manager",
                "department": "Sales",
                "email": "mohammed@example.com",
                "work_phone": "+966130000001",
                "mobile": "+966500000002",
                "is_primary": "on",
            },
        )
        self.assertEqual(contact.status_code, 302)
        saved = SourcingVendorContact.objects.get(vendor=vendor)
        self.assertTrue(saved.is_primary)
        self.assertEqual(saved.full_name, "Mohammed Ali")
        self.assertTrue(AuditEvent.objects.filter(action="sourcing.vendor.contact_created", object_id=str(vendor.pk)).exists())

    def test_vendor_create_is_progressive_and_can_seed_materials(self):
        self.client.force_login(self.owner_user)
        civil = SourcingMaterial.objects.create(
            company=self.company, code="MAT-CIV", name="Rebar", category="Civil", default_unit="ton"
        )
        electrical = SourcingMaterial.objects.create(
            company=self.company, code="MAT-ELC", name="Power Cable", category="Electrical", default_unit="m"
        )

        response = self.client.post(
            reverse("sourcing:vendor_create"),
            {
                "display_name": "Quick Source",
                "materials": [str(civil.pk), str(electrical.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company, display_name="Quick Source")
        self.assertTrue(vendor.code.startswith("VND-"))
        self.assertEqual(vendor.name, "Quick Source")
        self.assertEqual(vendor.mobile, "")
        self.assertEqual(vendor.email, "")
        self.assertEqual(vendor.cr_number, "")
        self.assertEqual(vendor.vat_number, "")
        self.assertEqual(
            set(SourcingVendorOffer.objects.filter(vendor=vendor, is_active=True).values_list("material_id", flat=True)),
            {civil.pk, electrical.pk},
        )

        # Even a completely blank create remains safe: the form generates a unique
        # reference identity so operators can complete the record later.
        blank = self.client.post(reverse("sourcing:vendor_create"), {})
        self.assertEqual(blank.status_code, 302)
        blank_vendor = SourcingVendor.objects.exclude(pk=vendor.pk).get(company=self.company)
        self.assertTrue(blank_vendor.code.startswith("VND-"))
        self.assertTrue(blank_vendor.name.startswith("Vendor VND-"))

    def test_vendor_create_can_add_new_materials_with_existing_or_new_category_type(self):
        self.client.force_login(self.owner_user)
        existing = SourcingMaterial.objects.create(
            company=self.company,
            code="MAT-EXISTING",
            name="Existing Cable",
            category="Electrical",
            default_unit="m",
        )

        response = self.client.post(
            reverse("sourcing:vendor_create"),
            {
                "display_name": "Inline Material Vendor",
                "materials": [str(existing.pk)],
                "new_materials-TOTAL_FORMS": "3",
                "new_materials-INITIAL_FORMS": "0",
                "new_materials-MIN_NUM_FORMS": "0",
                "new_materials-MAX_NUM_FORMS": "20",
                "new_materials-0-name": "Flexible Conduit",
                "new_materials-0-category": "Electrical",
                "new_materials-0-new_category": "",
                "new_materials-0-default_unit": "m",
                "new_materials-0-code": "",
                "new_materials-1-name": "Fire Blanket",
                "new_materials-1-category": "__new__",
                "new_materials-1-new_category": "Fire & Safety",
                "new_materials-1-default_unit": "pcs",
                "new_materials-1-code": "",
                # The browser immediately propagates a newly typed category/type to
                # the other inline rows.  This third row submits that same value as a
                # normal selection before it exists in the database.
                "new_materials-2-name": "Fire Extinguisher",
                "new_materials-2-category": "Fire & Safety",
                "new_materials-2-new_category": "",
                "new_materials-2-default_unit": "pcs",
                "new_materials-2-code": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company, display_name="Inline Material Vendor")
        conduit = SourcingMaterial.objects.get(company=self.company, name="Flexible Conduit")
        fire_blanket = SourcingMaterial.objects.get(company=self.company, name="Fire Blanket")
        extinguisher = SourcingMaterial.objects.get(company=self.company, name="Fire Extinguisher")
        self.assertEqual(conduit.category, "Electrical")
        self.assertEqual(conduit.default_unit, "m")
        self.assertTrue(conduit.code.startswith("MAT-"))
        self.assertEqual(fire_blanket.category, "Fire & Safety")
        self.assertEqual(fire_blanket.default_unit, "pcs")
        self.assertEqual(extinguisher.category, "Fire & Safety")
        self.assertEqual(extinguisher.default_unit, "pcs")
        self.assertEqual(
            set(SourcingVendorOffer.objects.filter(vendor=vendor).values_list("material_id", flat=True)),
            {existing.pk, conduit.pk, fire_blanket.pk, extinguisher.pk},
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                area=AuditArea.SOURCING,
                action="sourcing.material.created",
                object_id=str(conduit.pk),
            ).exists()
        )

        create_page = self.client.get(reverse("sourcing:vendor_create"))
        self.assertEqual(create_page.status_code, 200)
        self.assertContains(create_page, "All categories / types")
        self.assertContains(create_page, "Fire &amp; Safety")
        self.assertContains(create_page, "+ Add another material")

    def test_vendor_editor_without_master_manage_cannot_inline_create_material(self):
        editor, _membership = self._member(
            username="vendor-only-inline-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        page = self.client.get(reverse("sourcing:vendor_create"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "requires Reference Masters edit access")
        self.assertNotContains(page, "+ Add another material")

        response = self.client.post(
            reverse("sourcing:vendor_create"),
            {
                "display_name": "Should Not Save",
                "new_materials-TOTAL_FORMS": "1",
                "new_materials-INITIAL_FORMS": "0",
                "new_materials-MIN_NUM_FORMS": "0",
                "new_materials-MAX_NUM_FORMS": "20",
                "new_materials-0-name": "Unauthorized Material",
                "new_materials-0-category": "__new__",
                "new_materials-0-new_category": "Unauthorized Category",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingVendor.objects.filter(company=self.company, display_name="Should Not Save").exists())
        self.assertFalse(SourcingMaterial.objects.filter(company=self.company, name="Unauthorized Material").exists())

    def test_vendor_directory_shows_only_three_unique_material_types_and_searches_them(self):
        self.client.force_login(self.owner_user)
        vendor = SourcingVendor.objects.create(company=self.company, code="VND-TYPES", name="Typed Vendor")
        materials = [
            SourcingMaterial.objects.create(company=self.company, code="MAT-C1", name="Rebar", category="Civil"),
            SourcingMaterial.objects.create(company=self.company, code="MAT-C2", name="Cement", category="Civil"),
            SourcingMaterial.objects.create(company=self.company, code="MAT-E1", name="Cable", category="Electrical"),
            SourcingMaterial.objects.create(company=self.company, code="MAT-H1", name="Duct", category="HVAC"),
            SourcingMaterial.objects.create(company=self.company, code="MAT-P1", name="Gloves", category="PPE"),
        ]
        offers = [
            SourcingVendorOffer.objects.create(company=self.company, vendor=vendor, material=material)
            for material in materials
        ]
        now = timezone.now()
        # Preview ordering is deterministic: newest sourcing activity first. When two
        # types have the same activity timestamp, the higher recorded quantity wins.
        # Civil deliberately has the largest quantity but older activity, so it should
        # not crowd out more recently maintained material types.
        activity = [
            (now - timedelta(days=4), "100"),
            (now - timedelta(days=5), "150"),
            (now, "5"),
            (now - timedelta(days=1), "10"),
            (now, "50"),
        ]
        for offer, (updated_at, quantity) in zip(offers, activity, strict=True):
            SourcingVendorOffer.objects.filter(pk=offer.pk).update(
                updated_at=updated_at,
                available_quantity=quantity,
            )

        response = self.client.get(reverse("sourcing:vendor_list"))
        self.assertEqual(response.status_code, 200)
        listed = next(item for item in response.context["vendors"] if item.pk == vendor.pk)
        self.assertEqual(listed.material_type_preview, ["PPE", "Electrical", "HVAC"])
        self.assertEqual(listed.material_type_more_count, 1)
        self.assertContains(response, "Material Types")
        self.assertContains(response, "+1 more")

        type_search = self.client.get(reverse("sourcing:vendor_list"), {"q": "Electrical"})
        self.assertEqual(type_search.context["page_obj"].paginator.count, 1)
        self.assertContains(type_search, "Typed Vendor")

        material_search = self.client.get(reverse("sourcing:vendor_list"), {"q": "Cable"})
        self.assertEqual(material_search.context["page_obj"].paginator.count, 1)
        self.assertContains(material_search, "Typed Vendor")

        code_search = self.client.get(reverse("sourcing:vendor_list"), {"q": "MAT-E1"})
        self.assertEqual(code_search.context["page_obj"].paginator.count, 1)
        self.assertContains(code_search, "Typed Vendor")

    def test_vendor_lifecycle_is_reference_only_and_recoverable(self):
        self.client.force_login(self.owner_user)
        vendor = SourcingVendor.objects.create(company=self.company, code="VND-LIFE", name="Lifecycle Vendor")
        response = self.client.post(reverse("sourcing:vendor_status", args=[vendor.pk]), {"status": "inactive"})
        self.assertEqual(response.status_code, 302)
        vendor.refresh_from_db()
        self.assertEqual(vendor.status, SourcingEntityStatus.INACTIVE)

        self.client.post(reverse("sourcing:vendor_archive", args=[vendor.pk]), {"reason": "Not currently used"})
        vendor.refresh_from_db()
        self.assertIsNotNone(vendor.archived_at)
        self.client.post(reverse("sourcing:vendor_restore_archive", args=[vendor.pk]))
        vendor.refresh_from_db()
        self.assertIsNone(vendor.archived_at)

        self.client.post(
            reverse("sourcing:vendor_trash", args=[vendor.pk]),
            {"confirmation": vendor.code, "reason": "Created by mistake"},
        )
        vendor.refresh_from_db()
        self.assertIsNotNone(vendor.deleted_at)
        self.assertIsNotNone(vendor.purge_after)
        self.client.post(reverse("sourcing:vendor_restore_trash", args=[vendor.pk]))
        vendor.refresh_from_db()
        self.assertIsNone(vendor.deleted_at)
        self.assertIsNone(vendor.purge_after)
        self.assertTrue(AuditEvent.objects.filter(action="sourcing.vendor.trash_restored", object_id=str(vendor.pk)).exists())


    def test_archive_forces_inactive_and_contact_delete_is_permanent(self):
        self.client.force_login(self.owner_user)
        vendor = SourcingVendor.objects.create(company=self.company, code="VND-DEST", name="Destructive Lifecycle Vendor")
        contact = SourcingVendorContact.objects.create(
            company=self.company, vendor=vendor, first_name="Delete", last_name="Me", is_active=True
        )

        archived = self.client.post(
            reverse("sourcing:vendor_archive", args=[vendor.pk]),
            {"reason": "Temporarily not used"},
        )
        self.assertEqual(archived.status_code, 302)
        vendor.refresh_from_db()
        self.assertIsNotNone(vendor.archived_at)
        self.assertEqual(vendor.status, SourcingEntityStatus.INACTIVE)

        self.client.post(reverse("sourcing:vendor_restore_archive", args=[vendor.pk]))
        vendor.refresh_from_db()
        self.assertIsNone(vendor.archived_at)
        self.assertEqual(vendor.status, SourcingEntityStatus.INACTIVE)

        deleted = self.client.post(reverse("sourcing:vendor_contact_delete", args=[vendor.pk, contact.pk]))
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(SourcingVendorContact.objects.filter(pk=contact.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company, action="sourcing.vendor.contact_deleted", object_id=str(vendor.pk)
            ).exists()
        )

    def test_vendor_contact_cannot_cross_company_boundary(self):
        vendor = SourcingVendor.objects.create(company=self.company, code="VND-BOUND", name="Boundary Vendor")
        contact = SourcingVendorContact(
            company=self.other_company,
            vendor=vendor,
            first_name="Wrong Tenant",
        )
        with self.assertRaises(Exception):
            contact.full_clean()
