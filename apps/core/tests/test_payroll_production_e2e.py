from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class PayrollProductionE2ECertificationContractTests(SimpleTestCase):
    def test_certification_contract_matches_runtime_suite_and_release_gates(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-production-e2e.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Verified Payroll production-E2E certification", result.stdout)

    def test_high_risk_certification_scenarios_remain_registered(self):
        contract = json.loads((ROOT / "merge/payroll-production-e2e.json").read_text(encoding="utf-8"))
        scenario_ids = {row["id"] for row in contract["scenarios"]}
        required = {
            "access-and-workspace-authorization",
            "attendance-contract-and-submission",
            "internal-payroll-review-approval-integrity",
            "internal-wps-payment-reconciliation",
            "internal-master-lifecycle-recovery",
            "rental-assignment-timesheet-workflow",
            "rental-settlement-payment-integrity",
            "rental-master-lifecycle-recovery",
            "reports-documents-and-output-authority",
            "tenant-and-cross-module-boundaries",
            "seed-scale-and-performance-regression",
        }
        self.assertTrue(required.issubset(scenario_ids))
        self.assertGreaterEqual(len(contract["runtime_test_labels"]), 12)
