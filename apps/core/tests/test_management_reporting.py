from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.core.management import build_report, management_context
from apps.core.management_api import _csv_cell
from apps.core.models import Company


class ManagementReadModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Management Company", slug="management-company")
        self.period = date(2026, 8, 1)

    def test_empty_company_management_context_does_not_invent_financial_data(self):
        payload = management_context(company=self.company, period_start=self.period)
        self.assertEqual(payload["internal"]["net"], "0.00")
        self.assertEqual(payload["rental"]["net"], "0.00")
        self.assertFalse(payload["comparable"])
        self.assertIsNone(payload["combined"])
        self.assertEqual(payload["approvals"], [])
        self.assertEqual(payload["audit"], [])

    def test_reports_reject_cross_workspace_report_types(self):
        with self.assertRaises(ValueError):
            build_report(company=self.company, report_type="supplier-cost", period_start=self.period, workspace="internal")

    def test_csv_export_neutralizes_spreadsheet_formula_cells(self):
        self.assertEqual(_csv_cell("=2+2"), "'=2+2")
        self.assertEqual(_csv_cell("@SUM(A1:A2)"), "'@SUM(A1:A2)")
        self.assertEqual(_csv_cell("ordinary text"), "ordinary text")
