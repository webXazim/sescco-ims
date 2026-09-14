from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class PayrollQueryHardeningContractTests(SimpleTestCase):
    def test_postgresql_search_query_contract_is_frozen(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-payroll-query-hardening.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("Payroll PostgreSQL search/query hardening contract verified.", result.stdout)
