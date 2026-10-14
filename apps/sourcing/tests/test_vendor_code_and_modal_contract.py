"""Regression coverage for readable Vendor codes and safe onboarding drafts."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.models import SourcingVendor
from apps.sourcing.services.vendors import suggest_vendor_code
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class VendorCodeAndModalTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Vendor Code Test", slug="vendor-code-test")
        user = get_user_model().objects.create_user(username="vendor-code-owner", password="strong-pass")
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.OWNER)
        self.client.force_login(user)

    def test_automatically_named_vendor_has_readable_unique_code(self):
        page = self.client.get(reverse('sourcing:vendor_create'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-vendor-code-preview')
        self.assertNotContains(page, 'value="VND-')
        first = self.client.post(reverse('sourcing:vendor_create'), {"name": "Gulf Electrical Trading"})
        self.assertEqual(first.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company, name='Gulf Electrical Trading')
        self.assertEqual(vendor.code, 'VND-GULF-ELECTRICAL-TRADING')
        self.assertEqual(suggest_vendor_code(name="Gulf Electrical Trading", company=self.company),
                         'VND-GULF-ELECTRICAL-TRADING-2')

    def test_similar_names_get_suffix_and_manual_code_is_preserved(self):
        existing = SourcingVendor.objects.create(company=self.company, code='VND-GULF-ELECTRICAL-TRADING',
                                                 name='Existing Vendor')
        candidate = suggest_vendor_code(name='Gulf Electrical Trading', company=self.company)
        self.assertEqual(candidate, 'VND-GULF-ELECTRICAL-TRADING-2')
        response = self.client.post(reverse('sourcing:vendor_create'), {"name": "Gulf Electrical Trading"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SourcingVendor.objects.get(company=self.company, name='Gulf Electrical Trading').code, candidate)
        manual = self.client.post(reverse('sourcing:vendor_create'),
                                  {"name": "Independent Supplier", "code": "VND-CUSTOM-CODE"})
        self.assertEqual(manual.status_code, 302)
        self.assertTrue(SourcingVendor.objects.filter(company=self.company, code='VND-CUSTOM-CODE').exists())

    def test_blank_vendor_remains_supported_without_random_code(self):
        response = self.client.post(reverse('sourcing:vendor_create'), {})
        self.assertEqual(response.status_code, 302)
        vendor = SourcingVendor.objects.get(company=self.company)
        self.assertEqual(vendor.code, 'VND-UNNAMED')
        self.assertEqual(vendor.name, 'Vendor VND-UNNAMED')

    def test_modal_has_server_persisted_draft_confirmation_controls(self):
        page = self.client.get(reverse('sourcing:vendor_create'))
        for token in ('data-onboarding-confirm', 'data-onboarding-keep', 'data-onboarding-discard',
                      'data-onboarding-cancel', 'data-onboarding-done'):
            self.assertContains(page, token)
