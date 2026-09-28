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


    def test_row_action_menus_escape_table_overflow(self):
        base = (ROOT / "templates/sourcing/base.html").read_text(encoding="utf-8")
        script = (ROOT / "static/sourcing/js/directory-menus.js").read_text(encoding="utf-8")
        css = (ROOT / "static/sourcing/css/directory.css").read_text(encoding="utf-8")
        self.assertIn("sourcing/js/directory-menus.js", base)
        self.assertIn("document.body.appendChild(panel)", script)
        self.assertIn("availableBelow", script)
        self.assertIn("availableAbove", script)
        self.assertIn('document.addEventListener("scroll", schedulePosition, true)', script)
        self.assertIn("sourcing-row-menu__floating-panel", css)
        self.assertIn("position:fixed!important", css)

        for rel in (
            "templates/sourcing/vendors/list.html",
            "templates/sourcing/vendors/detail.html",
            "templates/sourcing/material_finder/list.html",
            "templates/sourcing/materials/list.html",
            "templates/sourcing/manpower/list.html",
            "templates/sourcing/manpower/detail.html",
            "templates/sourcing/workforce_finder/list.html",
            "templates/sourcing/trades/list.html",
        ):
            self.assertIn("sourcing-row-menu", (ROOT / rel).read_text(encoding="utf-8"))
