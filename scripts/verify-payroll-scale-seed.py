#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL SCALE SEED ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


helper_rel = "apps/core/management/payroll_seed_scale.py"
command_rel = "apps/core/management/commands/seed_payroll_test_data.py"
helper = text(helper_rel)
command = text(command_rel)
deploy = text("scripts/deploy-production.sh")
release_tasks = text("scripts/release-tasks.sh")
freeze = text("scripts/verify-production-freeze.sh")
ast.parse(helper)
ast.parse(command)

contract = json.loads(text("merge/payroll-scale-seed.json"))
if contract.get("release") != "1.0.61":
    fail("scale-seed contract release must be 1.0.61")
profiles = contract.get("profiles", {})
realistic = profiles.get("realistic", {})
benchmark = profiles.get("benchmark", {})
expected_realistic = {
    "internal_employees": 250,
    "rental_workers": 750,
    "branches": 6,
    "departments": 12,
    "suppliers": 8,
    "projects": 12,
    "months": 6,
}
expected_benchmark = {
    "internal_employees": 2000,
    "rental_workers": 5000,
    "branches": 15,
    "departments": 24,
    "suppliers": 30,
    "projects": 40,
    "months": 12,
}
if any(realistic.get(key) != value for key, value in expected_realistic.items()):
    fail("realistic profile sizes changed")
if any(benchmark.get(key) != value for key, value in expected_benchmark.items()):
    fail("benchmark profile sizes changed")

for required in (
    '"realistic": PayrollScaleProfile(',
    'internal_employees=250',
    'rental_workers=750',
    '"benchmark": PayrollScaleProfile(',
    'internal_employees=2000',
    'rental_workers=5000',
    'months=12',
    'INTERNAL_PREFIX = "DEMO-SCALE-I-"',
    'RENTAL_PREFIX = "RDEMO-SCALE-"',
    'ignore_conflicts=True',
    'def _effective_profile(',
    'def _verify(',
    'expected_internal_daily',
    'expected_rental_daily',
    'SalaryPaymentRow',
    'SupplierSettlementLine',
    'SupplierPaymentAllocation',
    'PayrollAdjustmentType.SALARY_ADVANCE',
    'RentalAdjustmentType.ADVANCE',
    'AssignmentChangeType.TRANSFER',
    'settlement_updates = []',
    'SupplierSettlement.objects.bulk_update(',
    'payment_updates = []',
    'SupplierPayment.objects.bulk_update(',
    'allocation_updates = []',
    'SupplierPaymentAllocation.objects.bulk_update(',
):
    if required not in helper:
        fail(f"scale helper missing required contract text: {required}")

for required in (
    'choices=("functional", "realistic", "benchmark")',
    'default=os.getenv("IMS_SEED_PROFILE", "functional")',
    'profile != "functional" and not clean_demo_company',
    'seed_payroll_scale_data(',
    'batch_size=options["seed_batch_size"]',
    'High-cardinality profiles deliberately commit in bounded chunks',
    '"--allow-mixed-scale-seed"',
    'self._assert_mixed_scale_window_is_safe(company, history_start, profile)',
    'Mixed scale seed refused because target benchmark months contain non-DEMO Internal payroll/attendance ',
):
    if required not in command:
        fail(f"seed command missing scale-profile contract: {required}")

for source, name in ((deploy, "deploy-production.sh"), (release_tasks, "release-tasks.sh")):
    for required in ("--seed-profile", "functional|realistic|benchmark", "--allow-mixed-scale-seed"):
        if required not in source:
            fail(f"{name} missing {required}")
if '--seed --seed-profile "${seed_profile}"' not in deploy:
    fail("deploy script does not forward the selected scale profile")
if 'seed_args+=(--profile "${seed_profile}")' not in release_tasks:
    fail("release tasks do not pass the scale profile to Django")
if 'release_args+=(--allow-mixed-scale-seed)' not in deploy:
    fail("deploy script does not forward mixed-scale override")
if 'seed_args+=(--allow-mixed-scale-seed)' not in release_tasks:
    fail("release tasks do not forward mixed-scale override to Django")
if contract.get("safety", {}).get("mixed_override_refuses_non_demo_internal_history_overlap") is not True:
    fail("scale-seed contract must require mixed-company history collision refusal")
if "verify-payroll-scale-seed.py" not in freeze:
    fail("production freeze does not run the scale-seed verifier")

print("Payroll scale-seed profile contract verified.")
