from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class FinalPayrollBrowserCertificationContractTests(SimpleTestCase):
    def test_final_payroll_browser_certification_contract_is_frozen(self):
        contract = json.loads((ROOT / "merge/payroll-final-browser-certification.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["release"], "1.0.77")
        self.assertEqual(contract["benchmark_volume"]["internal_employees"], 2000)
        self.assertEqual(contract["benchmark_volume"]["rental_workers"], 5000)
        self.assertEqual(contract["page_sizes"], [25, 50, 100])
        self.assertEqual(contract["max_rendered_business_rows"], 100)
        self.assertEqual(contract["max_assignment_expanded_rows"], 200)
        self.assertEqual(len(contract["certified_surfaces"]), 23)
        for surface in (
            "salary-setup-employee-structures",
            "payroll-runs-register",
            "internal-advances-adjustments",
            "salary-payments-register",
            "bank-readiness",
            "wps-readiness",
            "documents",
            "reports",
            "management-approval-center",
            "management-audit-trail",
        ):
            self.assertIn(surface, contract["certified_surfaces"])

        runner = (ROOT / "scripts/certify-payroll-browser-scale.py").read_text(encoding="utf-8")
        for scenario in (
            "internal-employee-directory",
            "salary-setup-employee-structures",
            "payroll-runs-register",
            "internal-advances-adjustments",
            "salary-payments-register",
            "bank-readiness",
            "wps-readiness",
            "documents",
            "reports",
            "management-audit-trail",
            "rental-workforce-directory",
            "rental-assignment-activity",
            "rental-project-timesheets",
            "global-server-search",
        ):
            self.assertIn(scenario, runner)
