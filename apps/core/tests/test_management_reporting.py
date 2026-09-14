from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.core.management import (
    build_report, build_report_page, management_context, management_summary_context,
    management_approval_page_context, management_audit_page_context,
)
from apps.core.management_api import _csv_cell
from apps.core.models import Company
from apps.internal_payroll.models import EmployeePaymentProfile, InternalEmployee, PaymentDestination
from apps.core.selectors.record_management import record_management_context, record_management_page_context


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
    def test_interactive_report_contract_is_server_paginated(self):
        report = build_report_page(
            company=self.company, report_type="internal-payroll", period_start=self.period, workspace="internal",
            query="", page=3, page_size=25,
        )
        self.assertEqual(report["meta"]["pageSize"], 25)
        self.assertEqual(report["meta"]["count"], 0)
        self.assertEqual(report["rows"], [])
        self.assertEqual(report["title"], "Internal Payroll")


    def test_interactive_wps_report_does_not_decrypt_payment_destinations(self):
        employee = InternalEmployee.objects.create(
            company=self.company, employee_number="DEMO-001", full_name="Demo Employee", joining_date=date(2024, 1, 1)
        )
        EmployeePaymentProfile.objects.create(
            company=self.company, employee=employee, destination_type=PaymentDestination.SALARY_CARD,
            account_holder_name="Demo Employee", bank_name="Demo Payroll Bank", bank_code="DEMO",
            salary_card_number="CARD-0001", wps_enabled=True,
        )
        with patch("apps.core.encryption.decrypt_text", side_effect=AssertionError("interactive WPS report must not decrypt destination secrets")):
            report = build_report_page(
                company=self.company, report_type="wps", period_start=self.period, workspace="internal",
                query="", page=1, page_size=25,
            )
        self.assertEqual(report["meta"]["count"], 1)
        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0][0], "DEMO-001")
        self.assertEqual(report["rows"][0][2], "Salary card")
        self.assertEqual(report["rows"][0][6], "Configured")
        self.assertEqual(report["kpis"][0], ["Profiles", 1])

    def test_management_shell_and_shared_record_registers_are_deferred_and_paginated(self):
        summary = management_summary_context(company=self.company, period_start=self.period)
        self.assertTrue(summary["deferredRecords"])
        self.assertEqual(summary["audit"], [])
        approvals = management_approval_page_context(company=self.company, page=3, page_size=25)
        self.assertEqual(approvals["surface"], "management_approvals_page")
        self.assertEqual(approvals["meta"]["pageSize"], 25)
        self.assertEqual(approvals["approvals"], [])
        audit = management_audit_page_context(company=self.company, page=2, page_size=25)
        self.assertEqual(audit["surface"], "management_audit_page")
        self.assertEqual(audit["meta"]["pageSize"], 25)
        self.assertEqual(audit["audit"], [])
        bootstrap = record_management_context(company=self.company, include_internal=True, include_rental=True)
        self.assertTrue(bootstrap["deferred"])
        self.assertEqual(bootstrap["archive"], [])
        page = record_management_page_context(company=self.company, workspace="internal", bucket="archive", page=4, page_size=25)
        self.assertEqual(page["surface"], "record_management_page")
        self.assertEqual(page["meta"]["pageSize"], 25)
        self.assertEqual(page["records"], [])
