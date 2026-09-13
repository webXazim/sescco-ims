from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class PayrollDataAuthorityContractTests(SimpleTestCase):
    def test_payroll_business_state_stays_server_authoritative(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-data-authority.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Verified Payroll data authority", result.stdout)

    def test_browser_storage_contract_is_ui_only(self):
        contract = json.loads((ROOT / "merge/payroll-data-authority.json").read_text(encoding="utf-8"))
        keys = contract["browser_storage_allowlist"]
        self.assertGreaterEqual(len(keys), 25)
        self.assertTrue(all(key.startswith("payroll-ui-") for key in keys))
        forbidden = ("employee-records", "attendance-records", "payroll-runs", "supplier-payments", "rental-settlements")
        self.assertFalse(any(any(term in key for term in forbidden) for key in keys))
