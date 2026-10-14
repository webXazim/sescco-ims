"""Manpower/Subcontractor full capability onboarding, save atomicity and tenant safety."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.models import (
    SourcingManpowerSupplier, SourcingWorkforceOffer, SourcingTrade,
    SourcingSubcontractor, SourcingSubcontractorService, SourcingService,
)
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ProviderCapabilityOnboardingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Capability Company', slug='provider-onboard')
        self.other = Company.objects.create(name='Outside Company', slug='provider-outside')
        user = get_user_model().objects.create_user(username='capability-onboard-owner', password='pass-not-used')
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.OWNER)
        self.client.force_login(user)

    def test_both_create_pages_expose_detailed_draft_editors(self):
        for route, kind in (('sourcing:manpower_supplier_create', 'trade'),
                            ('sourcing:subcontractor_create', 'service')):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-provider-onboarding')
            self.assertContains(response, f'data-kind="{kind}"')
            self.assertContains(response, 'data-onboarding-master')
            self.assertContains(response, 'provider-capability-onboarding.js')
            self.assertContains(response, 'supply_items-TOTAL_FORMS')

    def test_existing_workforce_reference_saved_with_supplier(self):
        trade = SourcingTrade.objects.create(company=self.company, code='TRD-EL', name='Electrician')
        payload = {
            'name': 'Eastern Workforce', 'tags': 'Electrical',
            'supply_items-TOTAL_FORMS': '1', 'supply_items-INITIAL_FORMS': '0',
            'supply_items-MIN_NUM_FORMS': '0', 'supply_items-MAX_NUM_FORMS': '50',
            'supply_items-0-trade': str(trade.pk),
            'supply_items-0-availability': 'available',
            'supply_items-0-available_quantity': '8',
            'supply_items-0-currency': 'SAR', 'supply_items-0-rate': '4000',
            'supply_items-0-rate_basis': 'month',
        }
        response = self.client.post(reverse('sourcing:manpower_supplier_create'), payload)
        self.assertEqual(response.status_code, 302, response.content[:1600])
        supplier = SourcingManpowerSupplier.objects.get(company=self.company)
        self.assertTrue(supplier.code.startswith('MPS-EASTERN-WORKFORCE'))
        self.assertEqual(supplier.tags, ['Electrical'])
        offer = SourcingWorkforceOffer.objects.get(company=self.company, supplier=supplier)
        self.assertEqual(offer.trade_id, trade.pk)
        self.assertEqual(offer.available_quantity, 8)

    def test_new_service_is_committed_with_subcontractor(self):
        payload = {
            'name': 'Quality Engineering',
            'supply_items-TOTAL_FORMS': '1', 'supply_items-INITIAL_FORMS': '0',
            'supply_items-MIN_NUM_FORMS': '0', 'supply_items-MAX_NUM_FORMS': '50',
            'supply_items-0-new_master_name': 'Pump Installation',
            'supply_items-0-new_master_category': '__new__',
            'supply_items-0-new_master_new_category': 'Mechanical',
            'supply_items-0-new_master_default_rate_basis': 'job',
            'supply_items-0-scope_description': 'Industrial pump alignment',
            'supply_items-0-availability': 'available',
            'supply_items-0-currency': 'SAR',
            'supply_items-0-rate_basis': 'job',
        }
        # The rate-basis enums depend on the controlled service choices.
        from apps.sourcing.models import SourcingServiceRateBasis
        basis = SourcingServiceRateBasis.choices[0][0]
        payload['supply_items-0-new_master_default_rate_basis'] = basis
        payload['supply_items-0-rate_basis'] = basis
        response = self.client.post(reverse('sourcing:subcontractor_create'), payload)
        self.assertEqual(response.status_code, 302, response.content[:1600])
        sub = SourcingSubcontractor.objects.get(company=self.company)
        service = SourcingService.objects.get(company=self.company)
        offer = SourcingSubcontractorService.objects.get(company=self.company, subcontractor=sub)
        self.assertEqual(offer.service_id, service.pk)
        self.assertEqual(offer.scope_description, 'Industrial pump alignment')
        self.assertTrue(sub.code.startswith('SUB-QUALITY-ENGINEERING'))

    def test_malformed_capability_prevents_partial_save(self):
        payload = {
            'name': 'Invalid Capability',
            'supply_items-TOTAL_FORMS': '1', 'supply_items-INITIAL_FORMS': '0',
            'supply_items-MIN_NUM_FORMS': '0', 'supply_items-MAX_NUM_FORMS': '50',
            'supply_items-0-service': 'not-a-uuid',
        }
        response = self.client.post(reverse('sourcing:subcontractor_create'), payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingSubcontractor.objects.filter(company=self.company, name='Invalid Capability').exists())

    def test_cannot_link_foreign_trade_on_create(self):
        trade = SourcingTrade.objects.create(company=self.other, code='FOREIGN-TRADE', name='Outside Trade')
        payload = {
            'name': 'Outsider Attempt', 'supply_items-TOTAL_FORMS': '1',
            'supply_items-INITIAL_FORMS': '0', 'supply_items-MIN_NUM_FORMS': '0',
            'supply_items-MAX_NUM_FORMS': '50',
            'supply_items-0-trade': str(trade.pk),
        }
        response = self.client.post(reverse('sourcing:manpower_supplier_create'), payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingManpowerSupplier.objects.filter(company=self.company, name='Outsider Attempt').exists())
