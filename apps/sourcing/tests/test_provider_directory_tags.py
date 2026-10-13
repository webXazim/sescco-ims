"""Regression coverage for provider classification tags and active master counts."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.sourcing.exchange import export_rows
from apps.sourcing.forms import SourcingVendorForm, SourcingManpowerSupplierForm, SourcingSubcontractorForm
from apps.sourcing.models import (
    SourcingVendor, SourcingMaterial, SourcingVendorOffer,
    SourcingManpowerSupplier, SourcingTrade, SourcingWorkforceOffer,
    SourcingSubcontractor, SourcingService, SourcingSubcontractorService,
)
from apps.sourcing.models.provider_tags import normalize_provider_tags
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class ProviderDirectoryTagTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Tag Providers', slug='tag-providers')
        self.other = Company.objects.create(name='Other Tags', slug='other-tags')
        user = get_user_model().objects.create_user(username='tags-owner', password='strong-tags-password')
        CompanyMembership.objects.create(company=self.company, user=user, role=AccessRole.OWNER)
        self.client.force_login(user)

    def test_tags_are_bounded_and_case_deduplicated(self):
        self.assertEqual(normalize_provider_tags([' electrical ', 'ELECTRICAL', 'Civil']), ['Electrical', 'Civil'])
        with self.assertRaises(ValidationError):
            normalize_provider_tags(['Tag '+str(n) for n in range(11)])
        with self.assertRaises(ValidationError):
            normalize_provider_tags(['Bad | Tag'])

    def test_company_tags_have_identical_forms_and_exact_filtering(self):
        objects = [
            (SourcingVendor, 'sourcing:vendor_list', 'Vendor A'),
            (SourcingManpowerSupplier, 'sourcing:manpower_supplier_list', 'Supplier B'),
            (SourcingSubcontractor, 'sourcing:subcontractor_list', 'Subcontractor C'),
        ]
        for index, (model, route, name) in enumerate(objects):
            provider = model.objects.create(company=self.company, name=name, code=f'TAG-{index}', tags=['Electrical', 'Safety'])
            model.objects.create(company=self.company, name=f'Other {index}', code=f'OTHER-{index}', tags=['Civil Works'])
            model.objects.create(company=self.other, name=f'Secret {index}', code=f'SECRET-{index}', tags=['Electrical'])
            page = self.client.get(reverse(route), {'tag': 'Electrical'})
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.context['page_obj'].paginator.count, 1)
            self.assertContains(page, name)
            self.assertNotContains(page, f'Secret {index}')
            self.assertContains(page, 'Company tag')
            self.assertContains(page, 'data-unified-form')
            find = self.client.get(reverse(route), {'q':'Safety'})
            self.assertEqual(find.context['page_obj'].paginator.count, 1)
            self.assertContains(find, name)
            incorrect = self.client.get(reverse(route), {'tag':'Civil'})
            self.assertEqual(incorrect.context['page_obj'].paginator.count, 0)
            self.assertEqual(provider.tags, ['Electrical', 'Safety'])

    def test_identical_create_and_edit_tag_validation_in_each_provider_form(self):
        for form_type, model, code in (
            (SourcingVendorForm, SourcingVendor, 'FORM-V'),
            (SourcingManpowerSupplierForm, SourcingManpowerSupplier, 'FORM-M'),
            (SourcingSubcontractorForm, SourcingSubcontractor, 'FORM-S'),
        ):
            form = form_type(data={'code': code, 'name': code, 'tags': 'electrical, Electrical, Civil'})
            self.assertTrue(form.is_valid(), form.errors.as_text())
            provider = form.save(commit=False)
            provider.company = self.company
            provider.save()
            self.assertEqual(provider.tags, ['Electrical', 'Civil'])
            edit = form_type(data={'code':code, 'name':code, 'tags':'Safety'}, instance=provider)
            self.assertTrue(edit.is_valid(), edit.errors.as_text())
            edit.save()
            provider.refresh_from_db()
            self.assertEqual(provider.tags, ['Safety'])

    def test_vendor_active_material_count_deduplicates_offers(self):
        vendor = SourcingVendor.objects.create(company=self.company, name='Electrician', code='ELEC', tags=['Electrical'])
        material = SourcingMaterial.objects.create(company=self.company, name='Cable', code='CABLE')
        SourcingVendorOffer.objects.create(company=self.company, vendor=vendor, material=material, specification='2mm')
        SourcingVendorOffer.objects.create(company=self.company, vendor=vendor, material=material, specification='4mm')
        response = self.client.get(reverse('sourcing:vendor_list'))
        self.assertEqual(response.context['vendors'][0].active_material_count, 1)
        self.assertContains(response, '1 material')

    def test_manpower_trade_and_subcontractor_service_counts_are_distinct(self):
        supplier = SourcingManpowerSupplier.objects.create(company=self.company, code='TRADES', name='Trades', tags=['Mechanical'])
        trade = SourcingTrade.objects.create(company=self.company, code='T-1', name='Welder')
        SourcingWorkforceOffer.objects.create(company=self.company, supplier=supplier, trade=trade)
        self.assertEqual(self.client.get(reverse('sourcing:manpower_supplier_list')).context['suppliers'][0].active_trade_count, 1)
        sub = SourcingSubcontractor.objects.create(company=self.company, code='SERVICES', name='Services', tags=['HVAC'])
        service = SourcingService.objects.create(company=self.company, code='S-1', name='Ducting')
        SourcingSubcontractorService.objects.create(company=self.company, subcontractor=sub, service=service)
        self.assertEqual(self.client.get(reverse('sourcing:subcontractor_list')).context['subcontractors'][0].active_service_type_count, 1)

    def test_tag_save_and_export_parity(self):
        vendor = SourcingVendor.objects.create(company=self.company, code='EXPORT1', name='Export Provider', tags=['Electrical'])
        response = self.client.get(reverse('sourcing:vendor_edit', args=[vendor.pk]))
        self.assertContains(response, 'value="Electrical"')
        rows = export_rows(company=self.company, dataset='vendors', params={'unified':'1', 'tag':'Electrical'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][-1], 'Electrical')
        self.assertEqual(export_rows(company=self.company, dataset='vendors', params={'unified':'1','tag':'Civil'}), [])
