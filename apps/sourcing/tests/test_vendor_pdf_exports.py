"""Read-only Vendor Sourcing PDF export authorization and data-scope tests."""
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
from apps.sourcing.models import SourcingMaterial, SourcingVendor, SourcingVendorOffer
from apps.sourcing.pdf_exports import company_report_rows, catalog_report_rows
from apps.sourcing.selectors.vendors import vendor_directory_page
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


class _ExportLinkParser(HTMLParser):
    """Extract rendered export URLs, not just route names in page HTML."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        values = dict(attrs)
        if 'data-unified-export' in values:
            self.links.append(values.get('href', ''))



@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class VendorPDFExportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PDF Source Company', slug='vendor-pdf-source')
        self.other = Company.objects.create(name='Other PDF Company', slug='vendor-pdf-other')
        self.owner = get_user_model().objects.create_user(username='vendor-pdf-owner', password='strong-test-password')
        CompanyMembership.objects.create(company=self.company, user=self.owner, role=AccessRole.OWNER)
        self.client.force_login(self.owner)
        self.vendor = SourcingVendor.objects.create(
            company=self.company, code='VPDF-1', name='Electrical Distributor',
            city='Dammam', region='Eastern Province', mobile='+966500000001',
            email='orders@example.test', tags=['Electrical'],
        )
        self.material = SourcingMaterial.objects.create(
            company=self.company, code='MAT-PDF-1', name='Industrial Cable', category='Electrical',
        )
        self.offer = SourcingVendorOffer.objects.create(
            company=self.company, vendor=self.vendor, material=self.material,
            specification='3 x 2.5 mm', available_quantity='120', unit='m',
            availability='available', rate='17.5000', currency='SAR', lead_time='3 days',
        )
        self.second = SourcingVendor.objects.create(company=self.company, code='VPDF-2', name='Plumbing Distributor', tags=['Mechanical'])
        self.other_vendor = SourcingVendor.objects.create(company=self.other, code='VPDF-OTHER', name='Secret Other Supplier')
        self.other_material = SourcingMaterial.objects.create(company=self.other, code='MAT-OTHER', name='Other Stock')
        SourcingVendorOffer.objects.create(company=self.other, vendor=self.other_vendor, material=self.other_material, rate='999')

    def _user_with_permissions(self, username, permissions):
        user = get_user_model().objects.create_user(username=username, password='strong-test-password')
        profile = AccessProfile.objects.create(company=self.company, key=f'profile-{username}', name=username, is_active=True)
        AccessProfilePermission.objects.bulk_create(
            AccessProfilePermission(profile=profile, permission=value) for value in permissions
        )
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.CUSTOM, access_profile=profile)
        return user

    def test_company_report_uses_directory_filters_and_has_exact_six_fields(self):
        query = vendor_directory_page(company=self.company, params={
            'tag': 'Electrical', 'status': 'active', 'page': '100', 'page_size': '25',
        }).page_obj.paginator.object_list
        rows = list(company_report_rows(query))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], (
            'Electrical Distributor', 'Dammam, Eastern Province', '+966500000001',
            'orders@example.test', 'Electrical', '1',
        ))
        response = self.client.get(reverse('sourcing:vendor_directory_pdf'), {'tag': 'Electrical', 'page': '100'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_vendor_catalog_pdf_contains_only_tenant_scoped_active_offers(self):
        rows = list(catalog_report_rows(
            SourcingVendorOffer.objects.for_company(self.company).filter(vendor=self.vendor, is_active=True).select_related('material')
        ))
        self.assertEqual(len(rows), 1)
        self.assertIn('Industrial Cable', rows[0][0])
        self.assertEqual(rows[0][2], 'Available')
        self.assertIn('SAR 17.5', rows[0][4])
        route = reverse('sourcing:vendor_catalog_pdf', args=[self.vendor.pk])
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.client.get(reverse('sourcing:vendor_catalog_pdf', args=[self.other_vendor.pk])).status_code, 404)
        self.offer.is_active = False
        self.offer.save(update_fields=['is_active'])
        # PDF still renders a well-formed, empty-catalog report.
        response = self.client.get(route)
        self.assertTrue(response.content.startswith(b'%PDF-'))

    def test_export_permission_is_required_in_addition_to_vendor_view(self):
        viewer = self._user_with_permissions('pdf-viewer', (AccessPermission.SOURCING_VENDORS_VIEW.value,))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('sourcing:vendor_directory_pdf')).status_code, 403)
        self.assertEqual(self.client.get(reverse('sourcing:vendor_catalog_pdf', args=[self.vendor.pk])).status_code, 403)
        exporter = self._user_with_permissions('pdf-exporter', (
            AccessPermission.SOURCING_VENDORS_VIEW.value, AccessPermission.SOURCING_EXPORT_EXECUTE.value,
        ))
        self.client.force_login(exporter)
        self.assertEqual(self.client.get(reverse('sourcing:vendor_directory_pdf')).status_code, 200)
        self.assertEqual(self.client.get(reverse('sourcing:vendor_catalog_pdf', args=[self.vendor.pk])).status_code, 200)

    def test_directory_export_links_have_valid_paths_with_and_without_filters(self):
        """A clean directory must not append request.path after the export URL."""
        expected_paths = {
            'sourcing:vendor_list': (
                reverse('sourcing:data_export', args=['vendors']),
                reverse('sourcing:vendor_directory_pdf'),
                reverse('sourcing:data_export', args=['vendor_catalog']),
            ),
            'sourcing:subcontractor_list': (
                reverse('sourcing:data_export', args=['subcontractors']),
                reverse('sourcing:data_export', args=['subcontractor_service_catalog']),
            ),
            'sourcing:manpower_supplier_list': (
                reverse('sourcing:data_export', args=['manpower_suppliers']),
                reverse('sourcing:data_export', args=['workforce_catalog']),
            ),
        }
        for name, expected in expected_paths.items():
            with self.subTest(directory=name):
                path = reverse(name)
                for params in ({}, {'q': 'Electrical', 'status': 'active', 'page': '3'}):
                    response = self.client.get(path, params)
                    self.assertEqual(response.status_code, 200)
                    links = _ExportLinkParser()
                    links.feed(response.content.decode('utf-8'))
                    self.assertEqual(len(links.links), len(expected))
                    for url, correct_path in zip(links.links, expected):
                        parsed = urlsplit(url)
                        self.assertEqual(parsed.path, correct_path)
                        self.assertNotIn(path, parsed.path.removeprefix(correct_path))
                        query = parse_qs(parsed.query)
                        self.assertNotIn('page', query)
                        if params:
                            self.assertEqual(query.get('q'), ['Electrical'])
                            self.assertEqual(query.get('status'), ['active'])
                        elif correct_path == reverse('sourcing:vendor_directory_pdf'):
                            self.assertEqual(parsed.query, '')

    def test_export_actions_only_render_for_authorized_users(self):
        page = self.client.get(reverse('sourcing:vendor_list'))
        self.assertContains(page, reverse('sourcing:vendor_directory_pdf'))
        detail = self.client.get(reverse('sourcing:vendor_detail', args=[self.vendor.pk]))
        self.assertContains(detail, reverse('sourcing:vendor_catalog_pdf', args=[self.vendor.pk]))
        viewer = self._user_with_permissions('pdf-no-export-ui', (AccessPermission.SOURCING_VENDORS_VIEW.value,))
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(reverse('sourcing:vendor_list')), reverse('sourcing:vendor_directory_pdf'))
        self.assertNotContains(self.client.get(reverse('sourcing:vendor_detail', args=[self.vendor.pk])), reverse('sourcing:vendor_catalog_pdf', args=[self.vendor.pk]))
