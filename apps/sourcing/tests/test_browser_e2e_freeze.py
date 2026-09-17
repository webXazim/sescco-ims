from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class SourcingBrowserE2EFreezeContractTests(SimpleTestCase):
    def test_final_sourcing_browser_contract_is_frozen(self):
        contract = json.loads((ROOT / "merge/sourcing-browser-e2e-production-freeze.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["release"], "1.0.117")
        self.assertFalse(contract["schema_change"])
        self.assertEqual(contract["permission_catalog_size"], 94)
        self.assertEqual(contract["persisted_model_retention_count"], 75)
        self.assertEqual(contract["required_seed_profile"], "benchmark")
        self.assertEqual(contract["browser_limits"]["max_rendered_business_rows"], 100)
        self.assertTrue(contract["browser_limits"]["stale_request_abort_required"])
        self.assertFalse(contract["operational_mutation_allowed"])
        self.assertTrue(contract["final_sourcing_feature_freeze"])
        self.assertEqual(len(contract["browser_scenarios"]), 13)

        runner = (ROOT / "scripts/certify-sourcing-browser-e2e.py").read_text(encoding="utf-8")
        for needle in (
            "SDEMO-V00001",
            "SDEMO Material 0001",
            "SDEMO-P00001",
            "SDEMO Trade 001",
            "vendor-supply-catalog",
            "material-finder",
            "vendor-quick-verification",
            "workforce-finder",
            "workforce-quick-verification",
            "sourcing-verification-timeline",
            "Save Verification",
        ):
            self.assertIn(needle, runner)
        for forbidden in ("/payroll/", "/inventory/", "/projects/", "/accounting/"):
            self.assertNotIn(forbidden, runner)
