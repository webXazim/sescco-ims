"""A category introduced in one unsaved capability can be reused by another.

No category/master is written outside the parent provider's atomic save.
"""
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.onboarding_categories import pending_master_categories
from apps.sourcing.models import (
    SourcingMaterial, SourcingVendor, SourcingVendorOffer,
    SourcingService, SourcingSubcontractor, SourcingSubcontractorService,
    SourcingTrade, SourcingManpowerSupplier, SourcingWorkforceOffer,
    SourcingServiceRateBasis,
)
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


class StagedCategoryExtractionTests(SimpleTestCase):
    def test_deleted_drafts_and_incomplete_sources_do_not_supply_categories(self):
        post = {
            'supply_items-TOTAL_FORMS': '4',
            'supply_items-0-new_material_name': 'First',
            'supply_items-0-new_material_category': '__new__',
            'supply_items-0-new_material_new_category': 'Electrical',
            'supply_items-1-new_material_name': 'Removed',
            'supply_items-1-new_material_category': '__new__',
            'supply_items-1-new_material_new_category': 'Deleted',
            'supply_items-1-DELETE': 'on',
            'supply_items-2-new_material_name': '',
            'supply_items-2-new_material_category': '__new__',
            'supply_items-2-new_material_new_category': 'Invalid',
            'supply_items-3-new_material_name': 'Another',
            'supply_items-3-new_material_category': '__new__',
            'supply_items-3-new_material_new_category': 'electrical',
        }
        self.assertEqual(pending_master_categories(
            post, category_field='new_material_category',
            new_category_field='new_material_new_category', name_field='new_material_name',
        ), ['Electrical'])


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class StagedCategoryOnboardingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Draft Categories Company', slug='draft-category-company')
        self.outside = Company.objects.create(name='External Categories Company', slug='outside-draft-category')
        user = get_user_model().objects.create_user(username='draft-category-owner', password='unused-password')
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.OWNER)
        self.client.force_login(user)
        self.management = {
            'supply_items-TOTAL_FORMS': '2', 'supply_items-INITIAL_FORMS': '0',
            'supply_items-MIN_NUM_FORMS': '0', 'supply_items-MAX_NUM_FORMS': '50',
        }

    def test_vendor_reuses_unsaved_material_category_in_second_draft(self):
        response = self.client.post(reverse('sourcing:vendor_create'), {
            **self.management, 'name': 'Reusable Vendor Categories',
            'supply_items-0-new_material_code': 'MAT-DRAFT-A',
            'supply_items-0-new_material_name': 'Copper Cable',
            'supply_items-0-new_material_category': '__new__',
            'supply_items-0-new_material_new_category': 'Electrical Components',
            'supply_items-0-currency': 'SAR',
            'supply_items-1-new_material_code': 'MAT-DRAFT-B',
            'supply_items-1-new_material_name': 'Cable Glands',
            'supply_items-1-new_material_category': 'Electrical Components',
            'supply_items-1-currency': 'SAR',
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'content', b'')[:1000])
        materials = SourcingMaterial.objects.filter(company=self.company)
        self.assertEqual(materials.count(), 2)
        self.assertEqual(set(materials.values_list('category', flat=True)), {'Electrical Components'})
        self.assertEqual(SourcingVendorOffer.objects.filter(company=self.company).count(), 2)
        self.assertFalse(SourcingMaterial.objects.filter(company=self.outside).exists())

    def test_reject_removed_or_unrelated_material_category(self):
        response = self.client.post(reverse('sourcing:vendor_create'), {
            **self.management, 'name': 'Invalid Draft Category Vendor',
            'supply_items-0-new_material_name': 'Removed Source',
            'supply_items-0-new_material_category': '__new__',
            'supply_items-0-new_material_new_category': 'Private Draft',
            'supply_items-0-DELETE': 'on',
            'supply_items-1-new_material_name': 'Would Be Orphan',
            'supply_items-1-new_material_category': 'Private Draft',
            'supply_items-1-currency': 'SAR',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SourcingVendor.objects.filter(company=self.company).exists())
        self.assertFalse(SourcingMaterial.objects.filter(company=self.company).exists())

    def test_subcontractor_reuses_unsaved_service_category_in_second_draft(self):
        basis = SourcingServiceRateBasis.choices[0][0]
        response = self.client.post(reverse('sourcing:subcontractor_create'), {
            **self.management, 'name': 'Reusable Service Categories',
            'supply_items-0-new_master_code': 'SRV-DRAFT-A',
            'supply_items-0-new_master_name': 'Pump Alignment',
            'supply_items-0-new_master_category': '__new__',
            'supply_items-0-new_master_new_category': 'Mechanical Services',
            'supply_items-0-new_master_default_rate_basis': basis,
            'supply_items-0-rate_basis': basis,
            'supply_items-0-currency': 'SAR',
            'supply_items-1-new_master_code': 'SRV-DRAFT-B',
            'supply_items-1-new_master_name': 'Motor Maintenance',
            'supply_items-1-new_master_category': 'Mechanical Services',
            'supply_items-1-new_master_default_rate_basis': basis,
            'supply_items-1-rate_basis': basis,
            'supply_items-1-currency': 'SAR',
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'content', b'')[:1000])
        self.assertEqual(SourcingService.objects.filter(company=self.company).count(), 2)
        self.assertEqual(set(SourcingService.objects.filter(company=self.company).values_list('category', flat=True)), {'Mechanical Services'})
        self.assertEqual(SourcingSubcontractorService.objects.filter(company=self.company).count(), 2)

    def test_trade_category_can_be_reused_by_another_trade(self):
        response = self.client.post(reverse('sourcing:manpower_supplier_create'), {
            **self.management, 'name': 'Reusable Trade Categories',
            'supply_items-0-new_master_code': 'TRD-DRAFT-A',
            'supply_items-0-new_master_name': 'Industrial Electrician',
            'supply_items-0-new_master_category': 'Electrical',
            'supply_items-0-currency': 'SAR',
            'supply_items-0-rate_basis': 'month',
            'supply_items-1-new_master_code': 'TRD-DRAFT-B',
            'supply_items-1-new_master_name': 'Cable Technician',
            'supply_items-1-new_master_category': 'Electrical',
            'supply_items-1-currency': 'SAR',
            'supply_items-1-rate_basis': 'month',
        })
        self.assertEqual(response.status_code, 302, getattr(response, 'content', b'')[:1000])
        self.assertEqual(set(SourcingTrade.objects.filter(company=self.company).values_list('category', flat=True)), {'Electrical'})
        self.assertEqual(SourcingWorkforceOffer.objects.filter(company=self.company).count(), 2)
