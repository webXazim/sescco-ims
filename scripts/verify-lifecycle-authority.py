#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"LIFECYCLE AUTHORITY ERROR: {message}")


def require(rel: str, text: str) -> None:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing {rel}")
    value = path.read_text(encoding="utf-8")
    if text not in value:
        fail(f"{rel} is missing {text!r}")


def forbid(rel: str, text: str) -> None:
    value = (ROOT / rel).read_text(encoding="utf-8")
    if text in value:
        fail(f"{rel} still contains retired local lifecycle logic {text!r}")


python_files = (
    "apps/core/services/lifecycle.py",
    "apps/core/services/__init__.py",
    "apps/core/tests/test_lifecycle_authority.py",
    "apps/internal_payroll/apps.py",
    "apps/internal_payroll/lifecycle.py",
    "apps/internal_payroll/services/organization.py",
    "apps/internal_payroll/selectors/organization.py",
    "apps/internal_payroll/api.py",
    "apps/internal_payroll/tests/test_organization.py",
)
for rel in python_files:
    ast.parse((ROOT / rel).read_text(encoding="utf-8"))

for rel, text in [
    ("apps/core/services/lifecycle.py", "class LifecycleAction(StrEnum):"),
    ("apps/core/services/lifecycle.py", "class LifecycleBlocker:"),
    ("apps/core/services/lifecycle.py", "class LifecycleDecision:"),
    ("apps/core/services/lifecycle.py", "class LifecyclePolicy:"),
    ("apps/core/services/lifecycle.py", "def register_lifecycle_policy("),
    ("apps/core/services/lifecycle.py", "def lifecycle_decision("),
    ("apps/core/services/lifecycle.py", "def lifecycle_capabilities("),
    ("apps/core/services/lifecycle.py", "def can_archive("),
    ("apps/core/services/lifecycle.py", "def can_restore("),
    ("apps/core/services/lifecycle.py", "def can_delete("),
    ("apps/core/services/lifecycle.py", "def delete_blockers("),
    ("apps/core/services/lifecycle.py", "def can_deactivate("),
    ("apps/core/services/lifecycle.py", "def archive_reason_required("),
    ("apps/core/services/lifecycle.py", "def record_lifecycle_action("),
    ("apps/core/services/lifecycle.py", '"dependency_counts": dict(decision.evidence)'),
    ("apps/internal_payroll/lifecycle.py", "class InternalEmployeeLifecyclePolicy(LifecyclePolicy):"),
    ("apps/internal_payroll/lifecycle.py", "register_lifecycle_policy(InternalEmployee, internal_employee_lifecycle_policy)"),
    ("apps/internal_payroll/apps.py", "from . import lifecycle  # noqa: F401"),
    ("apps/internal_payroll/services/organization.py", "require_lifecycle_action("),
    ("apps/internal_payroll/services/organization.py", "record_lifecycle_action("),
    ("apps/internal_payroll/selectors/organization.py", "def serialize_employee_lifecycle("),
    ("apps/internal_payroll/api.py", '"lifecycle": serialize_employee_lifecycle(employee)'),
    ("apps/core/tests/test_lifecycle_authority.py", "class LifecycleAuthorityTests(SimpleTestCase):"),
    ("apps/internal_payroll/tests/test_organization.py", "test_employee_uses_central_lifecycle_authority_and_audit_metadata"),
]:
    require(rel, text)

forbid("apps/internal_payroll/services/organization.py", "def _employee_delete_blockers(")

print("Central master-data lifecycle authority contract verified.")
