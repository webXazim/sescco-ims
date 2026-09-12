from django.test import SimpleTestCase

from apps.core.management.commands.seed_payroll_test_data import (
    INTERNAL_EMPLOYEES,
    RENTAL_WORKERS,
    WPS_HEADERS,
    _demo_iban,
)
from apps.internal_payroll.models import iban_is_valid


class PayrollSeedContractTests(SimpleTestCase):
    def test_seed_contains_both_internal_and_rental_reference_populations(self):
        self.assertEqual(len(INTERNAL_EMPLOYEES), 18)
        self.assertEqual(len(RENTAL_WORKERS), 30)
        self.assertEqual(len({row[0] for row in INTERNAL_EMPLOYEES}), 18)
        self.assertEqual(len({row[0] for row in RENTAL_WORKERS}), 30)

    def test_seed_wps_header_contract_matches_supported_source_shape(self):
        self.assertEqual(WPS_HEADERS, [
            "Bank", "Account Number", "Total Salary", "Transaction Reference", "Employee Name",
            "National ID/Iqama ID", "Employee Address", "Basic Salary", "Housing Allowance",
            "Other Earnings", "Deductions",
        ])

    def test_seed_generates_valid_unique_synthetic_saudi_ibans(self):
        values = {_demo_iban(index) for index in range(1, 20)}
        self.assertEqual(len(values), 19)
        self.assertTrue(all(value.startswith("SA") and iban_is_valid(value) for value in values))
