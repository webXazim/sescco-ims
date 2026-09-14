from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class PayrollBrowserScaleContractTests(SimpleTestCase):
    def test_5k_2k_browser_scale_contract_is_frozen(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-browser-scale.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Payroll 5K/2K browser-scale contract verified.", result.stdout)
