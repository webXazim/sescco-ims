from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class PayrollOutputE2EContractTests(SimpleTestCase):
    def test_output_contract_matches_frontend_backend_and_seed(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-output-e2e.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Verified Payroll output E2E contract", result.stdout)
