from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PayrollActionParityContractTests(SimpleTestCase):
    def test_registered_payroll_mutations_match_frontend_and_backend(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-action-parity.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Verified", result.stdout)

    def test_high_risk_actions_stay_registered(self):
        contract = json.loads((ROOT / "merge/payroll-action-parity.json").read_text(encoding="utf-8"))
        action_ids = {item["id"] for item in contract["rules"]}
        expected = {
            "internal.attendance.workflow",
            "internal.payroll.workflow",
            "internal.payment-batch.workflow",
            "internal.employee.lifecycle",
            "rental.timesheet.workflow",
            "rental.settlement.workflow",
            "rental.supplier-payment.result",
            "rental.project.lifecycle",
            "documents.finalize",
            "settings.company.update",
        }
        self.assertTrue(expected.issubset(action_ids))
        self.assertGreaterEqual(len(action_ids), 70)
