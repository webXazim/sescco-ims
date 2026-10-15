"""PDF report parity for the independent Sourcing provider directories."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.models import (
    SourcingManpowerSupplier, SourcingWorkforceOffer, SourcingTrade,
    SourcingSubcontractor, SourcingSubcontractorService, SourcingService,
)
from apps.sourcing.pdf_exports import (
    manpower_company_report_rows, subcontractor_company_report_rows,
    workforce_catalog_report_rows, subcontractor_catalog_report_rows,
)
from apps.sourcing.selectors.manpower import manpower_directory_page
from apps.sourcing.selectors.subcontractors import subcontractor_directory_page
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


class ExportLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pdf_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attributes = dict(attrs)
            if "data-unified-export-pdf" in attributes:
                self.pdf_links.append(attributes.get("href", ""))


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ProviderPDFParityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Source PDF Company", slug="provider-pdf-source")
        self.other = Company.objects.create(name="Other PDF Company", slug="provider-pdf-other")
        self.owner = get_user_model().objects.create_user(username="provider-pdf-owner", password="strong-test-password")
        CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.client.force_login(self.owner)
        self.manpower = SourcingManpowerSupplier.objects.create(
            company=self.company, name="Alpha Workforce", code="MPS-PDF-1", city="Riyadh",
            mobile="0500000000", email="manpower@example.test", tags=["Electrical"],
        )
        self.trade = SourcingTrade.objects.create(company=self.company, code="TRD-PDF-1", name="Electrician")
        self.workforce = SourcingWorkforceOffer.objects.create(
            company=self.company, supplier=self.manpower, trade=self.trade,
            availability="available", available_quantity=12, rate="250", currency="SAR", rate_basis="day",
            work_location="Riyadh", mobilization_lead_time="3 days",
        )
        self.subcontractor = SourcingSubcontractor.objects.create(
            company=self.company, code="SUB-PDF-1", name="Alpha Services", display_name="Alpha Services",
            city="Dammam", mobile="0550000000", email="services@example.test", tags=["HVAC"],
        )
        self.service = SourcingService.objects.create(company=self.company, code="SVC-PDF-1", name="AC Maintenance")
        self.service_offer = SourcingSubcontractorService.objects.create(
            company=self.company, subcontractor=self.subcontractor, service=self.service,
            availability="available", rate="800", currency="SAR", scope_description="Quarterly inspection",
            service_location="Dammam", lead_time="2 weeks",
        )
        self.other_manpower = SourcingManpowerSupplier.objects.create(company=self.other, code="MPS-OTHER", name="Other Workforce")
        self.other_subcontractor = SourcingSubcontractor.objects.create(company=self.other, code="SUB-OTHER", name="Other Services")

    def _user_with_permissions(self, username, permissions):
        user = get_user_model().objects.create_user(username=username, password="strong-test-password")
        profile = AccessProfile.objects.create(company=self.company, key=f"pdf-{username}", name=username, is_active=True)
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        ])
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_directory_pdf_uses_all_filtered_rows_and_six_columns(self):
        cases = (
            ("sourcing:manpower_supplier_list", "sourcing:manpower_directory_pdf", manpower_directory_page,
             manpower_company_report_rows, "Electrical", "Alpha Workforce", "12"),
            ("sourcing:subcontractor_list", "sourcing:subcontractor_directory_pdf", subcontractor_directory_page,
             subcontractor_company_report_rows, "HVAC", "Alpha Services", "1"),
        )
        for directory, export, selector, rows_fn, tag, expected_name, count in cases:
            with self.subTest(directory=directory):
                params = {"tag": tag, "status": "active", "page": "100", "page_size": "25"}
                qs = selector(company=self.company, params=params).page_obj.paginator.object_list
                rows = list(rows_fn(qs))
                self.assertEqual(len(rows), 1)
                self.assertEqual(len(rows[0]), 6)
                self.assertEqual(rows[0][0], expected_name)
                self.assertEqual(rows[0][4], tag)
                self.assertTrue(rows[0][5].isdigit())
                response = self.client.get(reverse(export), params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(b"%PDF-"))
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_individual_catalog_exports_tenant_scoped_and_active_only(self):
        directory_cases = (
            ("sourcing:workforce_catalog_pdf", self.manpower.pk, self.other_manpower.pk, "workforce"),
            ("sourcing:subcontractor_catalog_pdf", self.subcontractor.pk, self.other_subcontractor.pk, "service_offer"),
        )
        for route, own_id, other_id, offer_attr in directory_cases:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, args=[own_id]))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(b"%PDF-"))
                self.assertEqual(self.client.get(reverse(route, args=[other_id])).status_code, 404)
                offer = getattr(self, offer_attr)
                offer.is_active = False
                offer.save(update_fields=["is_active"])
                self.assertTrue(self.client.get(reverse(route, args=[own_id])).content.startswith(b"%PDF-"))

    def test_catalog_row_content_uses_corresponding_reference_type(self):
        workforce = list(workforce_catalog_report_rows(SourcingWorkforceOffer.objects.for_company(self.company).select_related("trade")))
        services = list(subcontractor_catalog_report_rows(SourcingSubcontractorService.objects.for_company(self.company).select_related("service")))
        self.assertEqual(len(workforce[0]), 7)
        self.assertIn("Electrician", workforce[0][0])
        self.assertIn("SAR 250", workforce[0][3])
        self.assertEqual(workforce[0][2], "12")
        self.assertEqual(len(services[0]), 7)
        self.assertIn("AC Maintenance", services[0][0])
        self.assertIn("Quarterly inspection", services[0][1])
        self.assertIn("SAR 800", services[0][4])

    def test_export_authority_required_besides_provider_view(self):
        for area, directory, catalog_id in (
            (AccessPermission.SOURCING_MANPOWER_VIEW.value, "sourcing:manpower_directory_pdf", "sourcing:workforce_catalog_pdf"),
            (AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value, "sourcing:subcontractor_directory_pdf", "sourcing:subcontractor_catalog_pdf"),
        ):
            with self.subTest(area=area):
                viewer = self._user_with_permissions(f"viewer-{len(area)}", (area,))
                self.client.force_login(viewer)
                self.assertEqual(self.client.get(reverse(directory)).status_code, 403)
                obj_id = self.manpower.pk if "manpower" in directory else self.subcontractor.pk
                self.assertEqual(self.client.get(reverse(catalog_id, args=[obj_id])).status_code, 403)
                exporter = self._user_with_permissions(f"exporter-{len(area)}", (area, AccessPermission.SOURCING_EXPORT_EXECUTE.value))
                self.client.force_login(exporter)
                self.assertEqual(self.client.get(reverse(directory)).status_code, 200)
                self.assertEqual(self.client.get(reverse(catalog_id, args=[obj_id])).status_code, 200)
        self.client.force_login(self.owner)

    def test_directory_pdf_link_valid_filtered_and_unfiltered(self):
        for directory_name, export_name in (
            ("sourcing:manpower_supplier_list", "sourcing:manpower_directory_pdf"),
            ("sourcing:subcontractor_list", "sourcing:subcontractor_directory_pdf"),
        ):
            with self.subTest(directory=directory_name):
                for params in ({}, {"q": "Alpha", "status": "active", "page": "3"}):
                    response = self.client.get(reverse(directory_name), params)
                    self.assertEqual(response.status_code, 200)
                    links = ExportLinks()
                    links.feed(response.content.decode("utf-8"))
                    self.assertEqual(len(links.pdf_links), 1)
                    parsed = urlsplit(links.pdf_links[0])
                    self.assertEqual(parsed.path, reverse(export_name))
                    query = parse_qs(parsed.query)
                    self.assertNotIn("page", query)
                    if params:
                        self.assertEqual(query.get("q"), ["Alpha"])
                    else:
                        self.assertEqual(parsed.query, "")

    def test_pdf_buttons_hidden_from_view_only_users(self):
        for view_permission, route, detail_name, obj in (
            (AccessPermission.SOURCING_MANPOWER_VIEW.value, "sourcing:manpower_directory_pdf", "sourcing:manpower_supplier_detail", self.manpower),
            (AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value, "sourcing:subcontractor_directory_pdf", "sourcing:subcontractor_detail", self.subcontractor),
        ):
            viewer = self._user_with_permissions(f"ui-{len(view_permission)}", (view_permission,))
            self.client.force_login(viewer)
            self.assertNotContains(self.client.get(reverse(detail_name, args=[obj.pk])), "Export catalog PDF")
            directory_path = "sourcing:manpower_supplier_list" if "manpower" in route else "sourcing:subcontractor_list"
            self.assertNotContains(self.client.get(reverse(directory_path)), reverse(route))
