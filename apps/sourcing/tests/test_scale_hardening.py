from __future__ import annotations

from django.test import TestCase

from apps.core.models import Company
from apps.sourcing.management.scale_seed import SCALE_PROFILES, seed_sourcing_scale_data
from apps.sourcing.models import SourcingManpowerSupplier, SourcingVendor
from apps.sourcing.selectors.materials import vendor_catalog_page
from apps.sourcing.selectors.vendors import vendor_directory_page
from apps.sourcing.selectors.workforce import workforce_catalog_page
from apps.sourcing.selectors.workforce_finder import workforce_finder_page


class SourcingScaleHardeningTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Scale Test", slug="sourcing-scale-test")

    def test_scale_profiles_freeze_expected_volumes(self):
        self.assertEqual(SCALE_PROFILES["benchmark"].vendors, 10_000)
        self.assertEqual(SCALE_PROFILES["benchmark"].materials, 2_000)
        self.assertEqual(SCALE_PROFILES["benchmark"].vendor_offers, 50_000)
        self.assertEqual(SCALE_PROFILES["benchmark"].manpower_suppliers, 5_000)
        self.assertEqual(SCALE_PROFILES["benchmark"].trades, 250)
        self.assertEqual(SCALE_PROFILES["benchmark"].workforce_offers, 25_000)

    def test_functional_seed_and_profile_catalogs_are_bounded(self):
        profile = SCALE_PROFILES["functional"]
        counts = seed_sourcing_scale_data(company=self.company, profile=profile, batch_size=200)
        self.assertGreaterEqual(counts["vendor_offers"], 100)
        vendor = SourcingVendor.objects.for_company(self.company).order_by("code").first()
        supplier = SourcingManpowerSupplier.objects.for_company(self.company).order_by("code").first()
        vendor_page, vendor_rows, _ = vendor_catalog_page(company=self.company, vendor=vendor, page=1, page_size=100)
        workforce_page, workforce_rows, _ = workforce_catalog_page(company=self.company, supplier=supplier, page=1, page_size=100)
        self.assertLessEqual(len(vendor_rows), 100)
        self.assertLessEqual(len(workforce_rows), 100)
        self.assertEqual(vendor_page.paginator.per_page, 100)
        self.assertEqual(workforce_page.paginator.per_page, 100)

    def test_directory_and_finder_pages_never_return_more_than_requested_page(self):
        seed_sourcing_scale_data(company=self.company, profile=SCALE_PROFILES["functional"], batch_size=200)
        vendors = vendor_directory_page(company=self.company, params={"q": "SDEMO", "page_size": 25}).page_obj
        workforce = workforce_finder_page(company=self.company, params={"q": "SDEMO", "page_size": 25}).page_obj
        self.assertLessEqual(len(list(vendors.object_list)), 25)
        self.assertLessEqual(len(list(workforce.object_list)), 25)
