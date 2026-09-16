from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.models import (
    SourcingEntityStatus,
    SourcingMaterial,
    SourcingSettings,
    SourcingVendor,
    SourcingVendorOffer,
)


class MaterialFinderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = Company.objects.create(name="Material Finder Co", slug="material-finder-co")
        self.other_company = Company.objects.create(name="Other Finder Co", slug="other-finder-co")
        self.owner_user = User.objects.create_user(username="finder-owner", password="strong-test-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.owner_user, role=AccessRole.OWNER)
        self.rebar = SourcingMaterial.objects.create(
            company=self.company,
            code="MAT-REB12",
            name="Rebar 12mm",
            category="Civil",
            default_unit="ton",
            aliases=["Steel Bar 12mm", "Reinforcement Bar"],
        )
        self.cable = SourcingMaterial.objects.create(
            company=self.company,
            code="MAT-CBL",
            name="Electrical Cable",
            category="Electrical",
            default_unit="m",
            aliases=["Power Cable"],
        )
        self.vendor_a = SourcingVendor.objects.create(
            company=self.company,
            code="VND-A",
            name="Eastern Steel Source",
            display_name="Eastern Steel",
            city="Dammam",
            region="Eastern Province",
        )
        self.vendor_b = SourcingVendor.objects.create(
            company=self.company,
            code="VND-B",
            name="Jubail Material Source",
            city="Jubail",
            region="Eastern Province",
        )
        SourcingSettings.objects.create(company=self.company, fresh_for_days=7, stale_after_days=30)

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

    def _offer(self, *, vendor=None, material=None, days=None, availability="available", rate="2180", qty="25"):
        return SourcingVendorOffer.objects.create(
            company=self.company,
            vendor=vendor or self.vendor_a,
            material=material or self.rebar,
            specification=f"Spec {days if days is not None else 'never'}",
            available_quantity=qty,
            unit="ton" if (material or self.rebar) == self.rebar else "m",
            availability=availability,
            rate=rate,
            currency="SAR",
            lead_time="1 day",
            last_verified_at=None if days is None else timezone.now() - timedelta(days=days),
        )

    def test_vendor_view_permission_controls_material_finder(self):
        viewer, _ = self._member(
            username="finder-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        master_only, _ = self._member(
            username="finder-master-only",
            permissions=(AccessPermission.SOURCING_MASTERS_VIEW.value,),
        )
        self._offer(days=1)

        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:material_finder"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Material Finder")
        self.assertContains(response, "Eastern Steel")
        self.assertNotContains(response, "Edit reference")

        self.client.force_login(master_only)
        self.assertEqual(self.client.get(reverse("sourcing:material_finder")).status_code, 403)

    def test_alias_search_and_company_vendor_lifecycle_isolation(self):
        viewer, _ = self._member(
            username="finder-alias-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        self._offer(vendor=self.vendor_a, days=1)
        self._offer(vendor=self.vendor_b, days=2, rate="2210", qty="40")

        inactive = SourcingVendor.objects.create(
            company=self.company,
            code="VND-INACTIVE",
            name="Inactive Steel Source",
            status=SourcingEntityStatus.INACTIVE,
        )
        self._offer(vendor=inactive, days=1)

        foreign_material = SourcingMaterial.objects.create(
            company=self.other_company,
            code="MAT-FOREIGN",
            name="Foreign Rebar",
            aliases=["Steel Bar 12mm"],
        )
        foreign_vendor = SourcingVendor.objects.create(
            company=self.other_company,
            code="VND-FOREIGN",
            name="Foreign Vendor",
        )
        SourcingVendorOffer.objects.create(
            company=self.other_company,
            vendor=foreign_vendor,
            material=foreign_material,
            availability="available",
            rate="1",
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("sourcing:material_finder"), {"q": "Steel Bar 12mm"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertContains(response, "Eastern Steel")
        self.assertContains(response, "Jubail Material Source")
        self.assertNotContains(response, "Inactive Steel Source")
        self.assertNotContains(response, "Foreign Vendor")

    def test_freshness_filters_use_company_policy(self):
        viewer, _ = self._member(
            username="finder-freshness-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        self._offer(vendor=self.vendor_a, days=2, rate="2000")
        self._offer(vendor=self.vendor_b, days=14, rate="2100")
        third = SourcingVendor.objects.create(company=self.company, code="VND-C", name="Old Vendor")
        fourth = SourcingVendor.objects.create(company=self.company, code="VND-D", name="Never Vendor")
        self._offer(vendor=third, days=60, rate="2200")
        self._offer(vendor=fourth, days=None, rate="2300")

        self.client.force_login(viewer)
        for key, expected_vendor in (
            ("fresh", "Eastern Steel"),
            ("needs-verification", "Jubail Material Source"),
            ("stale", "Old Vendor"),
            ("never", "Never Vendor"),
        ):
            response = self.client.get(reverse("sourcing:material_finder"), {"freshness": key})
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
            self.assertContains(response, expected_vendor)

    def test_finder_filters_and_server_pagination(self):
        viewer, _ = self._member(
            username="finder-filter-viewer",
            permissions=(AccessPermission.SOURCING_VENDORS_VIEW.value,),
        )
        self._offer(vendor=self.vendor_a, material=self.rebar, days=1, availability="available", rate="2100")
        self._offer(vendor=self.vendor_b, material=self.cable, days=1, availability="limited", rate="25", qty="500")
        for index in range(53):
            SourcingVendorOffer.objects.create(
                company=self.company,
                vendor=self.vendor_a,
                material=self.rebar,
                specification=f"Benchmark {index:03d}",
                availability="unknown",
            )

        self.client.force_login(viewer)
        filtered = self.client.get(
            reverse("sourcing:material_finder"),
            {"category": "Electrical", "availability": "limited", "location": "Jubail", "rate_max": "30"},
        )
        self.assertEqual(filtered.context["page_obj"].paginator.count, 1)
        self.assertContains(filtered, "Electrical Cable")

        page_two = self.client.get(
            reverse("sourcing:material_finder"),
            {"q": "Benchmark", "page_size": 50, "page": 2},
        )
        self.assertEqual(page_two.context["page_obj"].paginator.count, 53)
        self.assertEqual(len(page_two.context["offers"]), 3)

    def test_vendor_editor_gets_edit_action_from_finder(self):
        editor, _ = self._member(
            username="finder-editor",
            permissions=(
                AccessPermission.SOURCING_VENDORS_VIEW.value,
                AccessPermission.SOURCING_VENDORS_MANAGE.value,
            ),
        )
        offer = self._offer(days=1)
        self.client.force_login(editor)
        response = self.client.get(reverse("sourcing:material_finder"), {"q": "Rebar"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("sourcing:vendor_offer_edit", args=[self.vendor_a.pk, offer.pk]))
