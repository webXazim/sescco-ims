from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.core.management.commands.seed_payroll_test_data import (
    INTERNAL_EMPLOYEES,
    INTERNAL_HISTORY_EMPLOYEE_NUMBERS,
    RENTAL_WORKERS,
    WPS_HEADERS,
    _demo_iban,
    _seed_supplier_payment_date,
)
from apps.internal_payroll.models import iban_is_valid


class PayrollSeedContractTests(SimpleTestCase):
    def test_seed_contains_both_internal_and_rental_reference_populations(self):
        self.assertEqual(len(INTERNAL_EMPLOYEES), 18)
        self.assertEqual(len(RENTAL_WORKERS), 30)
        self.assertEqual(len({row[0] for row in INTERNAL_EMPLOYEES}), 18)
        self.assertEqual(len({row[0] for row in RENTAL_WORKERS}), 30)

    def test_history_cohort_is_only_the_base_internal_payroll_population(self):
        self.assertEqual(INTERNAL_HISTORY_EMPLOYEE_NUMBERS, tuple(row[0] for row in INTERNAL_EMPLOYEES))
        self.assertEqual(len(INTERNAL_HISTORY_EMPLOYEE_NUMBERS), 18)
        self.assertNotIn("DEMO-190", INTERNAL_HISTORY_EMPLOYEE_NUMBERS)
        self.assertNotIn("DEMO-192", INTERNAL_HISTORY_EMPLOYEE_NUMBERS)

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

    def test_seed_supplier_payment_date_never_precedes_live_approval(self):
        settlement = SimpleNamespace(approved_at=datetime(2026, 9, 12, 10, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(
            _seed_supplier_payment_date(settlement=settlement, period_start=datetime(2026, 8, 1).date()),
            datetime(2026, 9, 12).date(),
        )

    def test_seed_supplier_payment_date_keeps_period_end_when_approval_is_earlier(self):
        settlement = SimpleNamespace(approved_at=datetime(2026, 8, 20, 10, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(
            _seed_supplier_payment_date(settlement=settlement, period_start=datetime(2026, 8, 1).date()),
            datetime(2026, 8, 31).date(),
        )
