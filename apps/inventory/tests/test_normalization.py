from django.test import SimpleTestCase

from apps.inventory.normalization import clean_display_text, normalize_phone, normalize_text


class NormalizationTests(SimpleTestCase):
    def test_text_normalization_is_case_and_whitespace_insensitive(self):
        self.assertEqual(normalize_text("  GULF   Cement "), normalize_text("gulf cement"))

    def test_phone_normalization_matches_plus_and_double_zero_formats(self):
        self.assertEqual(normalize_phone("+966 57-368-6575"), "966573686575")
        self.assertEqual(normalize_phone("00966 (57) 368 6575"), "966573686575")

    def test_display_text_collapses_whitespace_without_lowercasing(self):
        self.assertEqual(clean_display_text("  Saudi   Supplier  "), "Saudi Supplier")
