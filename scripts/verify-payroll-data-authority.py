#!/usr/bin/env python3
"""Protect Payroll server authority and stale-response safety."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "static/payroll/js/app.js"
CONTRACT_PATH = ROOT / "merge/payroll-data-authority.json"


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DATA AUTHORITY ERROR: {message}")


try:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"cannot read contract: {exc}")

js = JS_PATH.read_text(encoding="utf-8")
allow = set(contract.get("browser_storage_allowlist") or [])
if not allow:
    fail("browser storage allowlist is empty")

literal_keys = set(re.findall(r"localStorage\.(?:getItem|setItem|removeItem)\(\s*['\"]([^'\"]+)['\"]", js))
unknown = sorted(literal_keys - allow)
missing = sorted(allow - literal_keys)
if unknown:
    fail(f"unclassified localStorage keys: {unknown}")
if missing:
    fail(f"allowlisted localStorage keys are no longer present; update the contract intentionally: {missing}")
if any(not key.startswith("payroll-ui-") for key in literal_keys):
    fail("Payroll localStorage contains a non-UI namespace")

# Dynamic localStorage use is permitted only for the workspace-period preference key.
dynamic_calls = []
for match in re.finditer(r"localStorage\.(?:getItem|setItem|removeItem)\(([^\n;]+)", js):
    arg = match.group(1).strip()
    if not (arg.startswith("'") or arg.startswith('"')):
        dynamic_calls.append(arg)
allowed_dynamic = {
    "state.workspace === 'rental' ? 'payroll-ui-rental-period' : state.workspace === 'management' ? 'payroll-ui-management-period' : 'payroll-ui-internal-period', state.period)",
}
if set(dynamic_calls) - allowed_dynamic:
    fail(f"unclassified dynamic localStorage access: {sorted(set(dynamic_calls) - allowed_dynamic)}")

# Never permit browser persistence helpers for business ledgers/masters to reappear.
for marker in (
    "function persistRentalTimesheets",
    "function persistRentalTimesheetStatuses",
    "function persistRentalOvertime",
    "function persistSupplierPayments",
    "function persistRentalWorkerState",
    "function persistRentalSettlements",
):
    if marker in js:
        fail(f"legacy browser business-state persistence marker returned: {marker}")

required_core = (
    "const payrollAuthorityGeneration = new Map();",
    "function payrollAuthorityTicket(domain, scope = '')",
    "function payrollAuthorityIsCurrent(ticket)",
    "function supersedePayrollAuthority(domain, scope = '')",
)
for marker in required_core:
    if marker not in js:
        fail(f"stale-response authority guard is missing: {marker}")

for domain in contract.get("authoritative_domains") or []:
    domain_id = domain.get("id")
    loader = domain.get("loader")
    apply = domain.get("apply")
    if not all((domain_id, loader, apply)):
        fail(f"invalid authoritative-domain declaration: {domain}")
    if f"function {loader}" not in js and f"async function {loader}" not in js:
        fail(f"loader missing for {domain_id}: {loader}")
    if f"function {apply}" not in js:
        fail(f"payload apply function missing for {domain_id}: {apply}")
    if f"payrollAuthorityTicket('{domain_id}'" not in js:
        fail(f"loader generation ticket missing for {domain_id}")
    if f"supersedePayrollAuthority('{domain_id}'" not in js:
        fail(f"mutation supersede marker missing for {domain_id}")

# Active-period finance state must not be activated by a response for another period.
for marker in (
    "const activate = paymentPeriodKey(state.period) === key;",
    "applyPaymentPayload(payload, { activate, supersede:false });",
    "const activate = state.period === period;",
    "applyRentalSettlementPayload(payload, { activate, supersede:false });",
):
    if marker not in js:
        fail(f"active-period authority guard missing: {marker}")

print(
    f"Verified Payroll data authority: {len(literal_keys)} UI-only browser-storage keys and "
    f"{len(contract.get('authoritative_domains') or [])} stale-response-protected server domains."
)
