"""Integration regressions for unified Sourcing company/catalog directories.

These tests deliberately exercise the HTTP entry points, tenants, filter queries,
and legacy bookmarks instead of testing a UI-only mock.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.exchange import export_rows
from apps.sourcing.models import (
    SourcingManpowerSupplier, SourcingMaterial, SourcingService,
    SourcingSubcontractor, SourcingSubcontractorService, SourcingTrade,
    SourcingVendor, SourcingVendorOffer, SourcingWorkforceOffer,
)
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class IntegratedSourcingDirectoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Consolidated Sourcing", slug="integrated-source")
        self.another = Company.objects.create(name="Another Source", slug="another-source")
        user = get_user_model().objects.create_user(
            username="integrated-sourcing-owner", password="strong-integrated-test-pass"
        )
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.OWNER)
        self.client.force_login(user)

        self.vendor = SourcingVendor.objects.create(company=self.company, code="IV001", name="Civil Supply")
        self.material = SourcingMaterial.objects.create(
            company=self.company, code="IM001", name="Rebar 16mm",
            category="Civil", aliases=["Reinforcement steel"],
        )
        self.vendor_offer = SourcingVendorOffer.objects.create(
            company=self.company, vendor=self.vendor, material=self.material,
            specification="B500B", rate="450", currency="SAR",
        )
        self.supplier = SourcingManpowerSupplier.objects.create(
            company=self.company, code="IP001", name="Labour Provider"
        )
        self.trade = SourcingTrade.objects.create(
            company=self.company, code="IT001", name="AC Technician", aliases=["HVAC Technician"],
        )
        self.workforce_offer = SourcingWorkforceOffer.objects.create(
            company=self.company, supplier=self.supplier, trade=self.trade, rate="150", currency="SAR",
        )
        self.subcontractor = SourcingSubcontractor.objects.create(
            company=self.company, code="IS001", name="Site Services"
        )
        self.service = SourcingService.objects.create(
            company=self.company, code="ISV001", name="Air Conditioning", aliases=["Cooling Works"],
        )
        self.service_offer = SourcingSubcontractorService.objects.create(
            company=self.company, subcontractor=self.subcontractor, service=self.service,
            scope_description="Duct supply and installation", rate="600", currency="SAR",
        )

    def test_main_company_views_search_catalog_aliases_without_duplicates(self):
        for route, search, expected in (
            ("sourcing:vendor_list", "Reinforcement steel", "Civil Supply"),
            ("sourcing:manpower_supplier_list", "HVAC Technician", "Labour Provider"),
            ("sourcing:subcontractor_list", "Cooling Works", "Site Services"),
        ):
            response = self.client.get(reverse(route), {"q": search, "sort": "code", "dir": "desc"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
            self.assertContains(response, expected)
            self.assertContains(response, 'name="sort"')
            self.assertNotContains(response, 'href="/app/sourcing/material-finder/"')
            self.assertNotContains(response, 'href="/app/sourcing/workforce-finder/"')
            self.assertNotContains(response, 'href="/app/sourcing/service-finder/"')

    def test_catalog_search_is_on_main_url_with_live_filters_and_page_limits(self):
        for route, search, expected in (
            ("sourcing:vendor_list", "Reinforcement steel", "Rebar 16mm"),
            ("sourcing:manpower_supplier_list", "HVAC Technician", "AC Technician"),
            ("sourcing:subcontractor_list", "Cooling Works", "Air Conditioning"),
        ):
            response = self.client.get(reverse(route), {
                "view": "offers", "q": search, "page_size": "99999",
                "sort": "unknown__unsafe", "dir": "invalid", "rate_min": "NaN",
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, expected)
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
            self.assertEqual(response.context["finder"].page_size, 50)
            self.assertContains(response, 'name="view" value="offers"')
            self.assertContains(response, 'data-sourcing-live-finder')
            self.assertContains(response, "view=offers")

    def test_old_finder_bookmarks_redirect_to_integrated_views(self):
        for old, new in (
            ("sourcing:material_finder", "sourcing:vendor_list"),
            ("sourcing:workforce_finder", "sourcing:manpower_supplier_list"),
            ("sourcing:service_finder", "sourcing:subcontractor_list"),
        ):
            response = self.client.get(reverse(old), {"q": "Steel", "freshness": "fresh"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].startswith(reverse(new) + "?"))
            self.assertIn("view=offers", response["Location"])
            self.assertIn("q=Steel", response["Location"])

    def test_company_and_offer_results_do_not_cross_tenant_boundary(self):
        hidden_vendor = SourcingVendor.objects.create(company=self.another, code="FOREIGN", name="Foreign Supplies")
        hidden_material = SourcingMaterial.objects.create(company=self.another, code="FOREIGNM", name="Secret Rebar")
        SourcingVendorOffer.objects.create(company=self.another, vendor=hidden_vendor, material=hidden_material)
        for params in ({"q": "Secret Rebar"}, {"view": "offers", "q": "Secret Rebar"}):
            response = self.client.get(reverse("sourcing:vendor_list"), params)
            self.assertEqual(response.context["page_obj"].paginator.count, 0)
            self.assertNotContains(response, "Foreign Supplies")

    def test_filtered_exports_match_catalog_alias_and_active_reference(self):
        self.assertEqual(
            len(export_rows(company=self.company, dataset="vendor_catalog", params={
                "view": "offers", "q": "Reinforcement steel"
            })), 1,
        )
        self.assertEqual(
            len(export_rows(company=self.company, dataset="vendors", params={
                "q": "Reinforcement steel", "status": "active"
            })), 1,
        )
        self.assertEqual(
            len(export_rows(company=self.company, dataset="manpower_suppliers", params={
                "q": "HVAC Technician", "status": "active"
            })), 1,
        )
        self.assertEqual(
            len(export_rows(company=self.company, dataset="subcontractors", params={
                "q": "Cooling Works", "status": "active"
            })), 1,
        )

    def test_server_pagination_is_bounded_and_sort_is_deterministic(self):
        # Many matching references still yield only the requested page, never
        # an unbounded set of rows in the directory response.
        vendors = [
            SourcingVendor.objects.create(
                company=self.company, code=f"IPAG-{i:04d}", name=f"Paging Vendor {i:04d}",
            ) for i in range(113)
        ]
        SourcingVendorOffer.objects.bulk_create([
            SourcingVendorOffer(
                company=self.company, vendor=vendor, material=self.material,
                specification=f"Bulk {index:04d}",
            ) for index, vendor in enumerate(vendors)
        ])
        response = self.client.get(reverse("sourcing:vendor_list"), {
            "view": "offers", "q": "Rebar 16mm", "page_size": "25", "page": "3",
            "sort": "vendor", "dir": "desc",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 114)
        self.assertEqual(len(response.context["offers"]), 25)
        self.assertContains(response, "Page 3 of 5")
        self.assertContains(response, "sort=vendor")
        self.assertContains(response, "view=offers")
