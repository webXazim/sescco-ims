from datetime import date

from django.test import SimpleTestCase

from apps.core.management.payroll_seed_scale import (
    SCALE_PROFILES,
    get_scale_profile,
    scale_months,
)


class PayrollSeedProfileContractTests(SimpleTestCase):
    def test_realistic_profile_is_large_but_operator_friendly(self):
        profile = get_scale_profile("realistic")
        self.assertEqual(profile.internal_employees, 250)
        self.assertEqual(profile.rental_workers, 750)
        self.assertEqual(profile.months, 6)
        self.assertEqual(profile.projects, 12)

    def test_benchmark_profile_exercises_thousands_of_workers_for_a_full_year(self):
        profile = get_scale_profile("benchmark")
        self.assertEqual(profile.internal_employees, 2000)
        self.assertEqual(profile.rental_workers, 5000)
        self.assertEqual(profile.months, 12)
        self.assertEqual(profile.projects, 40)
        self.assertEqual(profile.suppliers, 30)

    def test_scale_months_are_before_functional_history_and_oldest_first(self):
        months = scale_months(date(2026, 8, 1), 6)
        self.assertEqual(months[0], date(2026, 2, 1))
        self.assertEqual(months[-1], date(2026, 7, 1))
        self.assertNotIn(date(2026, 8, 1), months)

    def test_only_explicit_scale_profiles_are_available(self):
        self.assertEqual(set(SCALE_PROFILES), {"realistic", "benchmark"})
