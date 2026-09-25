from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.models import SourcingEntityStatus, SourcingManpowerContact, SourcingManpowerSupplier


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ManpowerSourcingMasterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Manpower Directory Co", slug="manpower-directory-co")
        self.other_company = Company.objects.create(name="Other Manpower Co", slug="other-manpower-co")
        self.owner_user = User.objects.create_user(username="manpower-owner", password="strong-test-password")
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

    def test_manpower_viewer_can_search_and_paginate_but_cannot_mutate(self):
        viewer, _membership = self._member(
            username="manpower-view-only",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        for index in range(55):
            SourcingManpowerSupplier.objects.create(
                company=self.company,
                code=f"MPS-{index:04d}",
                name=f"Manpower Supplier {index:04d}",
                email=f"manpower{index}@example.com",
            )
        SourcingManpowerSupplier.objects.create(company=self.other_company, code="MPS-OTHER", name="Other Tenant Manpower")

        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:manpower_supplier_list"), {"page_size": 50, "page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 55)
        self.assertEqual(len(response.context["suppliers"]), 5)
        self.assertNotContains(response, "Other Tenant Manpower")

        search = self.client.get(reverse("sourcing:manpower_supplier_list"), {"q": "manpower17@example.com"})
        self.assertEqual(search.context["page_obj"].paginator.count, 1)
        self.assertContains(search, "Manpower Supplier 0017")

        self.assertEqual(self.client.get(reverse("sourcing:manpower_supplier_create")).status_code, 403)
        target = SourcingManpowerSupplier.objects.for_company(self.company).first()
        self.assertEqual(
            self.client.post(reverse("sourcing:manpower_supplier_status", args=[target.pk]), {"status": "inactive"}).status_code,
            403,
        )

    def test_manpower_editor_creates_contacts_and_audit(self):
        editor, _membership = self._member(
            username="manpower-editor",
            permissions=(
                AccessPermission.SOURCING_MANPOWER_VIEW.value,
                AccessPermission.SOURCING_MANPOWER_MANAGE.value,
            ),
        )
        self.client.force_login(editor)
        create = self.client.post(
            reverse("sourcing:manpower_supplier_create"),
            {
                "code": "MPS-1001",
                "name": "Eastern Workforce Source",
                "primary_contact_name": "Ahmed Saleh",
                "phone": "+966500000001",
                "mobile": "",
                "email": "workforce@example.com",
                "city": "Dammam",
                "region": "Eastern Province",
                "cr_number": "CR-MPS-1001",
                "vat_number": "VAT-MPS-1001",
                "notes": "Reference manpower source only",
            },
        )
        self.assertEqual(create.status_code, 302)
        supplier = SourcingManpowerSupplier.objects.get(company=self.company, code="MPS-1001")
        self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING, action="sourcing.manpower_supplier.created", object_id=str(supplier.pk)).exists())

        contact = self.client.post(
            reverse("sourcing:manpower_contact_create", args=[supplier.pk]),
            {
                "salutation": "Mr",
                "first_name": "Mohammed",
                "last_name": "Ali",
                "designation": "Operations Manager",
                "department": "Operations",
                "email": "mohammed@example.com",
                "work_phone": "+966130000001",
                "mobile": "+966500000002",
                "is_primary": "on",
            },
        )
        self.assertEqual(contact.status_code, 302)
        saved = SourcingManpowerContact.objects.get(supplier=supplier)
        self.assertTrue(saved.is_primary)
        self.assertEqual(saved.full_name, "Mohammed Ali")
        self.assertTrue(AuditEvent.objects.filter(action="sourcing.manpower_supplier.contact_created", object_id=str(supplier.pk)).exists())

    def test_manpower_lifecycle_is_reference_only_and_recoverable(self):
        self.client.force_login(self.owner_user)
        supplier = SourcingManpowerSupplier.objects.create(company=self.company, code="MPS-LIFE", name="Lifecycle Manpower")
        response = self.client.post(reverse("sourcing:manpower_supplier_status", args=[supplier.pk]), {"status": "inactive"})
        self.assertEqual(response.status_code, 302)
        supplier.refresh_from_db()
        self.assertEqual(supplier.status, SourcingEntityStatus.INACTIVE)

        self.client.post(reverse("sourcing:manpower_supplier_archive", args=[supplier.pk]), {"reason": "Not currently used"})
        supplier.refresh_from_db()
        self.assertIsNotNone(supplier.archived_at)
        self.client.post(reverse("sourcing:manpower_supplier_restore_archive", args=[supplier.pk]))
        supplier.refresh_from_db()
        self.assertIsNone(supplier.archived_at)

        self.client.post(
            reverse("sourcing:manpower_supplier_trash", args=[supplier.pk]),
            {"confirmation": supplier.code, "reason": "Created by mistake"},
        )
        supplier.refresh_from_db()
        self.assertIsNotNone(supplier.deleted_at)
        self.assertIsNotNone(supplier.purge_after)
        self.client.post(reverse("sourcing:manpower_supplier_restore_trash", args=[supplier.pk]))
        supplier.refresh_from_db()
        self.assertIsNone(supplier.deleted_at)
        self.assertIsNone(supplier.purge_after)
        self.assertTrue(AuditEvent.objects.filter(action="sourcing.manpower_supplier.trash_restored", object_id=str(supplier.pk)).exists())


    def test_archive_forces_inactive_and_contact_delete_is_permanent(self):
        self.client.force_login(self.owner_user)
        supplier = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MPS-DEST", name="Destructive Lifecycle Supplier"
        )
        contact = SourcingManpowerContact.objects.create(
            company=self.company, supplier=supplier, first_name="Delete", last_name="Me", is_active=True
        )

        archived = self.client.post(
            reverse("sourcing:manpower_supplier_archive", args=[supplier.pk]),
            {"reason": "Temporarily not used"},
        )
        self.assertEqual(archived.status_code, 302)
        supplier.refresh_from_db()
        self.assertIsNotNone(supplier.archived_at)
        self.assertEqual(supplier.status, SourcingEntityStatus.INACTIVE)

        self.client.post(reverse("sourcing:manpower_supplier_restore_archive", args=[supplier.pk]))
        supplier.refresh_from_db()
        self.assertIsNone(supplier.archived_at)
        self.assertEqual(supplier.status, SourcingEntityStatus.INACTIVE)

        deleted = self.client.post(
            reverse("sourcing:manpower_contact_delete", args=[supplier.pk, contact.pk])
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(SourcingManpowerContact.objects.filter(pk=contact.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                company=self.company,
                action="sourcing.manpower_supplier.contact_deleted",
                object_id=str(supplier.pk),
            ).exists()
        )

    def test_manpower_contact_cannot_cross_company_boundary(self):
        supplier = SourcingManpowerSupplier.objects.create(company=self.company, code="MPS-BOUND", name="Boundary Manpower")
        contact = SourcingManpowerContact(
            company=self.other_company,
            supplier=supplier,
            first_name="Wrong Tenant",
        )
        with self.assertRaises(Exception):
            contact.full_clean()
