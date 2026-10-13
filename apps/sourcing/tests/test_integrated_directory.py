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

    def test_directory_search_uses_inventory_control_without_extra_copy(self):
        """Sourcing company views share Inventory's compact magnifier input."""
        for route in (
            "sourcing:vendor_list", "sourcing:manpower_supplier_list",
            "sourcing:subcontractor_list",
        ):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="search-field sourcing-directory-search"')
            self.assertContains(response, 'class="search-glyph"')
            self.assertContains(response, 'data-unified-form')
            self.assertContains(response, '<summary>Advanced filters</summary>')
            self.assertNotContains(response, 'sourcing-unified-intro')
            self.assertNotContains(response, 'Live search')
            self.assertNotContains(response, 'sourcing-unified-summary-help')
            self.assertNotContains(response, 'data-capabilities-slot')

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
        for route, search, provider, label in (
            ("sourcing:vendor_list", "Reinforcement steel", self.vendor, "Rebar 16mm"),
            ("sourcing:manpower_supplier_list", "HVAC Technician", self.supplier, "AC Technician"),
            ("sourcing:subcontractor_list", "Cooling Works", self.subcontractor, "Air Conditioning"),
        ):
            response = self.client.get(reverse(route), {
                "q": search, "page_size": "99999", "sort": "unknown__unsafe",
                "dir": "invalid", "rate_min": "NaN",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
            self.assertEqual(response.context["directory"].page_size, 50)
            self.assertContains(response, 'data-unified-form')
            self.assertContains(response, 'data-unified-results')
            self.assertContains(response, f'data-provider-row="{provider.pk}"')
            self.assertNotContains(response, 'sourcing-directory-views')
            detail = self.client.get(reverse(route), {
                "fragment": "capabilities", "provider": provider.pk, "q": search,
            })
            self.assertEqual(detail.status_code, 200)
            self.assertContains(detail, label)
            self.assertContains(detail, 'Verification history')

    def test_all_directory_columns_are_controllable_and_header_actions_grouped(self):
        """Columns cover the whole company table, with a shared header action group."""
        column_keys = (
            'provider', 'contact', 'email', 'location', 'tags',
            'capabilities', 'status', 'updated', 'actions',
        )
        for route, phone_key, label in (
            ('sourcing:vendor_list', 'mobile', 'Vendor'),
            ('sourcing:manpower_supplier_list', 'phone', 'Manpower Supplier'),
            ('sourcing:subcontractor_list', 'mobile', 'Subcontractor'),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'sourcing-page-head--directory')
                self.assertContains(response, 'class="sourcing-page-actions"')
                self.assertContains(response, 'data-columns-all')
                self.assertContains(response, 'data-columns-compact')
                self.assertContains(response, 'Export companies')
                self.assertContains(response, 'Export capabilities')
                self.assertContains(response, label)
                for column in (*column_keys, phone_key):
                    self.assertContains(response, f'data-column-toggle="{column}"')
                    self.assertContains(response, f'data-column="{column}"', count=2)

    def test_old_finder_bookmarks_redirect_to_integrated_views(self):
        for old, new in (
            ("sourcing:material_finder", "sourcing:vendor_list"),
            ("sourcing:workforce_finder", "sourcing:manpower_supplier_list"),
            ("sourcing:service_finder", "sourcing:subcontractor_list"),
        ):
            response = self.client.get(reverse(old), {"q": "Steel", "freshness": "fresh"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].startswith(reverse(new) + "?"))
            self.assertNotIn("view=offers", response["Location"])
            self.assertIn("q=Steel", response["Location"])
            old_tab = self.client.get(reverse(new), {"view": "offers", "q": "Steel"})
            self.assertEqual(old_tab.status_code, 302)
            self.assertNotIn("view=offers", old_tab["Location"])

    def test_company_and_offer_results_do_not_cross_tenant_boundary(self):
        hidden_vendor = SourcingVendor.objects.create(company=self.another, code="FOREIGN", name="Foreign Supplies")
        hidden_material = SourcingMaterial.objects.create(company=self.another, code="FOREIGNM", name="Secret Rebar")
        SourcingVendorOffer.objects.create(company=self.another, vendor=hidden_vendor, material=hidden_material)
        response = self.client.get(reverse("sourcing:vendor_list"), {"q": "Secret Rebar"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.assertNotContains(response, "Foreign Supplies")
        self.assertEqual(self.client.get(reverse('sourcing:vendor_list'), {
            'fragment': 'capabilities', 'provider': hidden_vendor.pk,
        }).status_code, 404)

    def test_capability_filters_match_one_offer_and_preserve_company_result(self):
        other = SourcingMaterial.objects.create(company=self.company, code='IM002', name='Paint', category='Finishes')
        SourcingVendorOffer.objects.create(company=self.company, vendor=self.vendor, material=other,
                                           rate='50', availability='available')
        # Category and rate must be satisfied by ONE offer, not two offers from the same vendor.
        route = reverse('sourcing:vendor_list')
        mismatch = self.client.get(route, {'category': 'Civil', 'rate_max': '100', 'availability': 'available'})
        self.assertEqual(mismatch.context['page_obj'].paginator.count, 0)
        match = self.client.get(route, {'category': 'Finishes', 'rate_max': '100', 'availability': 'available'})
        self.assertEqual(match.context['page_obj'].paginator.count, 1)
        self.assertContains(match, 'Civil Supply')
        detail = self.client.get(route, {'fragment': 'capabilities', 'provider': self.vendor.pk,
                                         'category': 'Finishes', 'rate_max': '100'})
        self.assertContains(detail, 'Paint')
        self.assertNotContains(detail, 'Rebar 16mm')
        exported = export_rows(company=self.company, dataset='vendor_catalog', params={
            'unified': '1', 'category': 'Finishes', 'rate_max': '100', 'availability': 'available',
        })
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0][1], 'IM002')

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
        vendors = [
            SourcingVendor.objects.create(company=self.company, code=f"IPAG-{i:04d}",
                                         name=f"Paging Vendor {i:04d}") for i in range(113)
        ]
        SourcingVendorOffer.objects.bulk_create([
            SourcingVendorOffer(company=self.company, vendor=vendor, material=self.material,
                                specification=f"Bulk {index:04d}") for index, vendor in enumerate(vendors)
        ])
        response = self.client.get(reverse("sourcing:vendor_list"), {
            "q": "Rebar 16mm", "page_size": "25", "page": "3", "sort": "name", "dir": "desc",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 114)
        self.assertEqual(len(response.context["vendors"]), 25)
        self.assertContains(response, "Page 3 of 5")
        self.assertContains(response, 'data-unified-results')
        self.assertNotContains(response, 'view=offers')

    def test_status_and_pagination_links_preserve_filters_without_duplicates(self):
        from html import unescape
        from html.parser import HTMLParser
        from urllib.parse import urlsplit, parse_qs
        from django.test import RequestFactory
        from apps.sourcing.templatetags.sourcing_directory_urls import sourcing_directory_url

        class StatusLinks(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_status = False
                self.links = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'div' and 'sourcing-status-strip' in attrs.get('class', '').split():
                    self.in_status = True
                if self.in_status and tag == 'a':
                    self.links.append(attrs['href'])

            def handle_endtag(self, tag):
                if tag == 'div' and self.in_status:
                    self.in_status = False

        for route in ('sourcing:vendor_list', 'sourcing:manpower_supplier_list',
                      'sourcing:subcontractor_list'):
            page = self.client.get(reverse(route), {'q': '', 'category': 'Civil', 'status': 'active'})
            self.assertEqual(page.status_code, 200)
            parser = StatusLinks()
            parser.feed(page.content.decode())
            self.assertGreaterEqual(len(parser.links), 3)
            for href in parser.links:
                query = parse_qs(urlsplit(unescape(href)).query)
                self.assertEqual(len(query.get('status', [])), 1)
                self.assertEqual(query.get('category'), ['Civil'])
                self.assertNotIn('page', query)

        request = RequestFactory().get('/app/sourcing/vendors/', {'q': 'Rebar', 'page': 5,
            'status': 'active', 'category': 'Civil'})
        link = sourcing_directory_url({'request': request}, page=2)
        params = parse_qs(urlsplit(link).query)
        self.assertEqual(params['page'], ['2'])
        self.assertEqual(params['status'], ['active'])
        self.assertEqual(params['category'], ['Civil'])
        self.assertEqual(params['q'], ['Rebar'])
