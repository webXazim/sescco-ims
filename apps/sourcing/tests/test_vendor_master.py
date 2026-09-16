from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import SourcingEntityStatus, SourcingVendor, SourcingVendorContact


@override_settings(SECURE_SSL_REDIRECT=False)
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
                "primary_contact_name": "Ahmed Saleh",
                "phone": "+966500000001",
                "mobile": "",
                "email": "sales@example.com",
                "city": "Dammam",
                "region": "Eastern Province",
                "cr_number": "CR1001",
                "vat_number": "VAT1001",
                "website": "https://example.com",
                "notes": "Reference vendor only",
            },
        )
        self.assertEqual(create.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company, code="VND-1001")
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

    def test_vendor_contact_cannot_cross_company_boundary(self):
        vendor = SourcingVendor.objects.create(company=self.company, code="VND-BOUND", name="Boundary Vendor")
        contact = SourcingVendorContact(
            company=self.other_company,
            vendor=vendor,
            first_name="Wrong Tenant",
        )
        with self.assertRaises(Exception):
            contact.full_clean()
