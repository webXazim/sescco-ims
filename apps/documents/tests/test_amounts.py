from django.test import SimpleTestCase

from apps.documents.services.amounts import money_to_words


class MoneyToWordsTests(SimpleTestCase):
    def test_salary_reference_amount_is_rendered_cleanly(self):
        self.assertEqual(
            money_to_words("2415.00", "SAR"),
            "Two Thousand Four Hundred Fifteen Saudi Riyals Only",
        )

    def test_halalas_are_preserved(self):
        self.assertEqual(
            money_to_words("5666.61", "SAR"),
            "Five Thousand Six Hundred Sixty Six Saudi Riyals and Sixty One Halalas Only",
        )
