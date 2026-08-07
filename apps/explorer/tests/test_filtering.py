from datetime import date

from django.test import SimpleTestCase

from apps.explorer.filtering import resolve_date_range


class DatePresetTests(SimpleTestCase):
    def setUp(self):
        self.today = date(2026, 8, 7)

    def test_today(self):
        result = resolve_date_range("today", today=self.today)
        self.assertEqual((result.start, result.end), (self.today, self.today))

    def test_this_week_starts_monday(self):
        result = resolve_date_range("this_week", today=self.today)
        self.assertEqual(result.start, date(2026, 8, 3))
        self.assertEqual(result.end, self.today)

    def test_month_and_quarter(self):
        self.assertEqual(resolve_date_range("this_month", today=self.today).start, date(2026, 8, 1))
        self.assertEqual(
            resolve_date_range("this_quarter", today=self.today).start,
            date(2026, 7, 1),
        )

    def test_previous_year(self):
        result = resolve_date_range("previous_year", today=self.today)
        self.assertEqual((result.start, result.end), (date(2025, 1, 1), date(2025, 12, 31)))

    def test_custom_range_is_inclusive(self):
        result = resolve_date_range(
            "custom", start=date(2026, 1, 1), end=date(2026, 1, 31), today=self.today
        )
        self.assertEqual(result.start, date(2026, 1, 1))
        self.assertEqual(result.end, date(2026, 1, 31))
