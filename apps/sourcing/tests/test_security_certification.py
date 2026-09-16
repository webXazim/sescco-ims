from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.utils import NotSupportedError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_profiles import create_access_profile, update_access_profile
from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.accounts.selectors import ACTIVE_COMPANY_SESSION_KEY
from apps.accounts.security import SESSION_SECURITY_VERSION_KEY
from apps.core.models import Company
from apps.sourcing.isolation import FORBIDDEN_OPERATIONAL_APP_LABELS
from apps.sourcing.models import (
    SourcingEntityStatus,
    SourcingManpowerSupplier,
    SourcingMaterial,
    SourcingTrade,
    SourcingVendor,
    SourcingVendorOfferRevision,
    SourcingWorkforceOfferRevision,
)
from apps.sourcing.selectors.material_finder import material_finder_page
from apps.sourcing.selectors.workforce_finder import workforce_finder_page
from apps.sourcing.services.catalog import create_material, create_vendor_offer, verify_vendor_offer
from apps.sourcing.services.manpower import (
    archive_manpower_supplier,
    create_manpower_supplier,
    trash_manpower_supplier,
)
from apps.sourcing.services.vendors import archive_vendor, create_vendor, trash_vendor
from apps.sourcing.services.workforce import create_trade, create_workforce_offer, verify_workforce_offer


@override_settings(SINGLE_COMPANY_MODE=False)
class SourcingSecurityCertificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Certification Company A", slug="sourcing-cert-a")
        self.other_company = Company.objects.create(name="Certification Company B", slug="sourcing-cert-b")
        self.owner_user = User.objects.create_user(username="sourcing-cert-owner", password="OwnerPass!2026")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.other_owner = CompanyMembership.objects.create(company=self.other_company, user=self.owner_user, role=AccessRole.OWNER)

    def _membership(self, *, username: str, permissions: tuple[str, ...], company=None):
        company = company or self.company
        User = get_user_model()
        user = User.objects.create_user(username=username, password="StrongPass!2026")
        actor = self.owner if company.pk == self.company.pk else self.other_owner
        profile = create_access_profile(
            actor_membership=actor,
            payload={"name": f"{username} profile", "permissions": list(permissions)},
        )
        membership = CompanyMembership.objects.create(
            company=company,
            user=user,
            role=AccessRole.CUSTOM,
            access_profile=profile,
        )
        return user, membership, profile

    def _client_for(self, user, company=None) -> Client:
        company = company or self.company
        client = Client()
        client.force_login(user)
        session = client.session
        session[ACTIVE_COMPANY_SESSION_KEY] = str(company.pk)
        session.save()
        return client

    def _operational_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        labels = set(FORBIDDEN_OPERATIONAL_APP_LABELS)
        # Accounting is not currently a standalone installed app in SESCCO MS; if it
        # becomes one later, this certification automatically includes it.
        if apps.is_installed("apps.accounting"):
            labels.add("accounting")
        for app_label in sorted(labels):
            config = apps.get_app_config(app_label)
            for model in config.get_models():
                if not model._meta.managed or model._meta.proxy:
                    continue
                counts[model._meta.label_lower] = model._default_manager.count()
        return counts

    def _seed_reference_pair(self):
        material = create_material(
            actor_membership=self.owner,
            cleaned_data={"code": "CERT-MAT", "name": "Certification Rebar", "default_unit": "ton"},
        )
        vendor = create_vendor(
            actor_membership=self.owner,
            cleaned_data={"code": "CERT-VND", "name": "Certification Vendor"},
        )
        vendor_offer = create_vendor_offer(
            actor_membership=self.owner,
            vendor_id=vendor.pk,
            cleaned_data={
                "material": material,
                "available_quantity": 25,
                "availability": "available",
                "rate": 2200,
                "currency": "SAR",
            },
            verified_now=True,
            contact_name="Vendor Contact",
        )
        trade = create_trade(
            actor_membership=self.owner,
            cleaned_data={"code": "CERT-TRD", "name": "Certification Steel Fixer", "category": "Civil"},
        )
        supplier = create_manpower_supplier(
            actor_membership=self.owner,
            cleaned_data={"code": "CERT-MPS", "name": "Certification Manpower"},
        )
        workforce_offer = create_workforce_offer(
            actor_membership=self.owner,
            supplier_id=supplier.pk,
            cleaned_data={
                "trade": trade,
                "available_quantity": 20,
                "availability": "available",
                "rate": 2400,
                "currency": "SAR",
                "rate_basis": "month",
            },
            verified_now=True,
            contact_name="Manpower Contact",
        )
        return vendor, material, vendor_offer, supplier, trade, workforce_offer

    def test_vendor_and_manpower_permissions_are_mutually_isolated(self):
        vendor_user, _membership, _profile = self._membership(
            username="cert-vendor-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        vendor_client = self._client_for(vendor_user)
        self.assertEqual(vendor_client.get(reverse("sourcing:vendor_list")).status_code, 200)
        self.assertEqual(vendor_client.get(reverse("sourcing:material_finder")).status_code, 200)
        self.assertEqual(vendor_client.get(reverse("sourcing:manpower_supplier_list")).status_code, 403)
        self.assertEqual(vendor_client.get(reverse("sourcing:workforce_finder")).status_code, 403)

        manpower_user, _membership, _profile = self._membership(
            username="cert-manpower-viewer",
            permissions=(AccessPermission.SOURCING_MANPOWER_VIEW.value,),
        )
        manpower_client = self._client_for(manpower_user)
        self.assertEqual(manpower_client.get(reverse("sourcing:manpower_supplier_list")).status_code, 200)
        self.assertEqual(manpower_client.get(reverse("sourcing:workforce_finder")).status_code, 200)
        self.assertEqual(manpower_client.get(reverse("sourcing:vendor_list")).status_code, 403)
        self.assertEqual(manpower_client.get(reverse("sourcing:material_finder")).status_code, 403)

    def test_company_a_cannot_read_company_b_sourcing_records(self):
        other_vendor = SourcingVendor.objects.create(company=self.other_company, code="B-VND", name="Company B Vendor")
        other_supplier = SourcingManpowerSupplier.objects.create(company=self.other_company, code="B-MPS", name="Company B Manpower")
        client = self._client_for(self.owner_user, self.company)
        self.assertEqual(client.get(reverse("sourcing:vendor_detail", args=[other_vendor.pk])).status_code, 404)
        self.assertEqual(client.get(reverse("sourcing:manpower_supplier_detail", args=[other_supplier.pk])).status_code, 404)

    def test_view_only_profiles_cannot_mutate_via_direct_post(self):
        vendor, _material, vendor_offer, supplier, _trade, workforce_offer = self._seed_reference_pair()
        user, _membership, _profile = self._membership(
            username="cert-view-only",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_MANPOWER_VIEW.value,
                AccessPermission.SOURCING_MASTERS_VIEW.value,
            ),
        )
        client = self._client_for(user)
        before = {
            "vendors": SourcingVendor.objects.for_company(self.company).count(),
            "suppliers": SourcingManpowerSupplier.objects.for_company(self.company).count(),
            "materials": SourcingMaterial.objects.for_company(self.company).count(),
            "trades": SourcingTrade.objects.for_company(self.company).count(),
            "vendor_revisions": SourcingVendorOfferRevision.objects.for_company(self.company).count(),
            "workforce_revisions": SourcingWorkforceOfferRevision.objects.for_company(self.company).count(),
        }
        requests = (
            ("sourcing:vendor_create", (), {"code": "DENY-V", "name": "Denied Vendor"}),
            ("sourcing:manpower_supplier_create", (), {"code": "DENY-M", "name": "Denied Manpower"}),
            ("sourcing:material_create", (), {"code": "DENY-MAT", "name": "Denied Material"}),
            ("sourcing:trade_create", (), {"code": "DENY-TRD", "name": "Denied Trade"}),
            ("sourcing:vendor_offer_verify", (vendor.pk, vendor_offer.pk), {"availability": "available"}),
            ("sourcing:workforce_offer_verify", (supplier.pk, workforce_offer.pk), {"availability": "available"}),
        )
        for name, args, data in requests:
            response = client.post(reverse(name, args=args), data=data)
            self.assertEqual(response.status_code, 403, name)
        after = {
            "vendors": SourcingVendor.objects.for_company(self.company).count(),
            "suppliers": SourcingManpowerSupplier.objects.for_company(self.company).count(),
            "materials": SourcingMaterial.objects.for_company(self.company).count(),
            "trades": SourcingTrade.objects.for_company(self.company).count(),
            "vendor_revisions": SourcingVendorOfferRevision.objects.for_company(self.company).count(),
            "workforce_revisions": SourcingWorkforceOfferRevision.objects.for_company(self.company).count(),
        }
        self.assertEqual(after, before)

    def test_archived_and_trash_sources_never_leak_into_finders(self):
        material = create_material(actor_membership=self.owner, cleaned_data={"code": "F-MAT", "name": "Finder Rebar"})
        trade = create_trade(actor_membership=self.owner, cleaned_data={"code": "F-TRD", "name": "Finder Electrician"})

        visible_vendor = create_vendor(actor_membership=self.owner, cleaned_data={"code": "F-V1", "name": "Visible Vendor"})
        archived_vendor = create_vendor(actor_membership=self.owner, cleaned_data={"code": "F-V2", "name": "Archived Vendor"})
        trashed_vendor = create_vendor(actor_membership=self.owner, cleaned_data={"code": "F-V3", "name": "Trashed Vendor"})
        visible_supplier = create_manpower_supplier(actor_membership=self.owner, cleaned_data={"code": "F-M1", "name": "Visible Manpower"})
        archived_supplier = create_manpower_supplier(actor_membership=self.owner, cleaned_data={"code": "F-M2", "name": "Archived Manpower"})
        trashed_supplier = create_manpower_supplier(actor_membership=self.owner, cleaned_data={"code": "F-M3", "name": "Trashed Manpower"})

        vendor_offers = []
        for vendor in (visible_vendor, archived_vendor, trashed_vendor):
            vendor_offers.append(create_vendor_offer(
                actor_membership=self.owner,
                vendor_id=vendor.pk,
                cleaned_data={"material": material, "availability": "available"},
                verified_now=False,
            ))
        workforce_offers = []
        for supplier in (visible_supplier, archived_supplier, trashed_supplier):
            workforce_offers.append(create_workforce_offer(
                actor_membership=self.owner,
                supplier_id=supplier.pk,
                cleaned_data={"trade": trade, "availability": "available", "rate_basis": "month"},
                verified_now=False,
            ))

        archive_vendor(actor_membership=self.owner, vendor_id=archived_vendor.pk, reason="certification")
        trash_vendor(actor_membership=self.owner, vendor_id=trashed_vendor.pk, confirmation=trashed_vendor.code, reason="certification")
        archive_manpower_supplier(actor_membership=self.owner, supplier_id=archived_supplier.pk, reason="certification")
        trash_manpower_supplier(actor_membership=self.owner, supplier_id=trashed_supplier.pk, confirmation=trashed_supplier.code, reason="certification")

        material_result = material_finder_page(company=self.company, params={"q": "Finder Rebar", "page_size": "100"})
        self.assertEqual([row.pk for row in material_result.page_obj.object_list], [vendor_offers[0].pk])
        workforce_result = workforce_finder_page(company=self.company, params={"q": "Finder Electrician", "page_size": "100"})
        self.assertEqual([row.pk for row in workforce_result.page_obj.object_list], [workforce_offers[0].pk])

    def test_verification_history_is_immutable_for_both_catalogs(self):
        _vendor, _material, vendor_offer, _supplier, _trade, workforce_offer = self._seed_reference_pair()
        vendor_revision = SourcingVendorOfferRevision.objects.for_company(self.company).filter(offer_id_snapshot=vendor_offer.pk).first()
        workforce_revision = SourcingWorkforceOfferRevision.objects.for_company(self.company).filter(offer_id_snapshot=workforce_offer.pk).first()
        self.assertIsNotNone(vendor_revision)
        self.assertIsNotNone(workforce_revision)
        with self.assertRaises(NotSupportedError):
            SourcingVendorOfferRevision.objects.filter(pk=vendor_revision.pk).update(note="tamper")
        with self.assertRaises(NotSupportedError):
            SourcingWorkforceOfferRevision.objects.filter(pk=workforce_revision.pk).delete()

    def test_sourcing_access_profile_change_revokes_stale_session(self):
        user, _membership, profile = self._membership(
            username="cert-session-user",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        client = self._client_for(user)
        first = client.get(reverse("sourcing:vendor_list"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(client.session[SESSION_SECURITY_VERSION_KEY], user.security_version)
        old_version = user.security_version
        update_access_profile(
            actor_membership=self.owner,
            profile_id=profile.pk,
            payload={"permissions": [AccessPermission.SOURCING_MANPOWER_VIEW.value]},
        )
        user.refresh_from_db()
        self.assertGreater(user.security_version, old_version)
        stale = client.get(reverse("sourcing:vendor_list"))
        self.assertEqual(stale.status_code, 302)
        self.assertTrue(stale.url.startswith(reverse("accounts:login")))

    def test_sourcing_create_and_verify_paths_do_not_mutate_operational_apps(self):
        before = self._operational_counts()
        vendor, _material, vendor_offer, supplier, _trade, workforce_offer = self._seed_reference_pair()
        verify_vendor_offer(
            actor_membership=self.owner,
            vendor_id=vendor.pk,
            offer_id=vendor_offer.pk,
            cleaned_data={"availability": "limited", "available_quantity": 15, "verification_note": "certified"},
            contact_name="Vendor Contact",
        )
        verify_workforce_offer(
            actor_membership=self.owner,
            supplier_id=supplier.pk,
            offer_id=workforce_offer.pk,
            cleaned_data={"availability": "limited", "available_quantity": 12, "verification_note": "certified"},
            contact_name="Manpower Contact",
        )
        after = self._operational_counts()
        self.assertEqual(after, before)
