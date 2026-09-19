#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL RENTAL FINANCE RUNTIME ERROR: {message}")

def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")

version = text("VERSION").strip()
contract = json.loads(text("merge/payroll-rental-finance-runtime.json"))
if contract.get("release") != version:
    fail("runtime contract release does not match VERSION")

js = text("static/payroll/js/app.js")
api = text("apps/rental_manpower/api.py")
selectors = text("apps/rental_manpower/selectors/settlements.py")

for needle in (
    "rentalSettlementDetailKeys: new Set()",
    "rentalSettlementErrorByPeriod: {}",
    "async function loadRentalSettlementProjectDetail(projectId, period = state.period",
    "detail:'1'",
    "state.rentalSettlementDetailKeys.add(detailKey)",
    "data-rental-settlement-retry",
    "Supplier settlements unavailable",
    "Supplier payments unavailable",
    "const t=group.totals||rentalSettlementTotals(group.rows||[]);",
):
    if needle not in js:
        fail(f"frontend runtime protection missing: {needle}")

# The Projects/Suppliers directory request blocks must remain independent of the selected
# finance period; otherwise opening a 4K-worker directory can trigger the full settlement rollup.
projects_block = js[js.index("} else if (kind === 'projects') {"):js.index("} else if (kind === 'suppliers') {")]
suppliers_block = js[js.index("} else if (kind === 'suppliers') {"):js.index("} else if (kind === 'workers') {")]
if "params.set('period'" in projects_block:
    fail("Projects directory reintroduced period financial rollup")
if "params.set('period'" in suppliers_block:
    fail("Suppliers directory reintroduced period financial rollup")

for needle in (
    "detail = str(request.GET.get(\"detail\", \"\"))",
    "if detail and not project_id:",
    "include_rows=detail",
    "include_adjustments=False",
    "include_payments=not detail",
):
    if needle not in api:
        fail(f"settlement API detail boundary missing: {needle}")

for needle in (
    "include_rows: bool = False",
    "if include_rows:",
    "include_rows=include_rows",
    '"rows": [serialize_settlement_line(line) for line in getattr(settlement, "snapshot_lines", [])] if include_rows else [],',
    "Summary mode computes advance totals with one aggregate query",
):
    if needle not in selectors:
        fail(f"bounded settlement selector missing: {needle}")

print("Verified Rental finance runtime: fast master directories, bounded settlement/payment summary, lazy project detail and retryable failures.")
