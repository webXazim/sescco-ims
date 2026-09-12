#!/usr/bin/env python3
"""Static release contract for SESCCO MS secondary Payroll configuration lifecycle."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"secondary configuration lifecycle verification failed: {message}")


def text(path: str) -> str:
    file = ROOT / path
    if not file.is_file():
        fail(f"missing {path}")
    return file.read_text(encoding="utf-8")


def require(path: str, *needles: str) -> None:
    body = text(path)
    for needle in needles:
        if needle not in body:
            fail(f"{path} is missing: {needle}")


def parse(path: str) -> None:
    try:
        ast.parse(text(path), filename=path)
    except SyntaxError as exc:
        fail(f"{path} is not valid Python: {exc}")


for path in (
    "apps/internal_payroll/models/salary.py",
    "apps/internal_payroll/models/payment.py",
    "apps/internal_payroll/lifecycle.py",
    "apps/internal_payroll/services/salary.py",
    "apps/internal_payroll/services/payment.py",
    "apps/internal_payroll/selectors/salary.py",
    "apps/internal_payroll/selectors/payment.py",
    "apps/internal_payroll/salary_api.py",
    "apps/internal_payroll/payment_api.py",
):
    parse(path)

require(
    "apps/internal_payroll/models/salary.py",
    "archived_at = models.DateTimeField",
    "archived_reason = models.CharField",
    "int_sal_comp_archive_idx",
    "int_ot_policy_archive_idx",
    "An archived salary component cannot be active.",
    "An archived overtime policy cannot be active.",
)
require(
    "apps/internal_payroll/models/payment.py",
    "int_bank_template_archive_idx",
    "An archived bank/WPS export template cannot be active.",
)
require(
    "apps/internal_payroll/lifecycle.py",
    "class SalaryComponentLifecyclePolicy",
    "class OvertimePolicyLifecyclePolicy",
    "class BankExportTemplateLifecyclePolicy",
    "class EmployeePaymentProfileLifecyclePolicy",
    '"active_overtime_policies"',
    '"salary_structure_lines"',
    '"payment_batches"',
    '"salary_payment_rows"',
)
require(
    "apps/internal_payroll/services/salary.py",
    "def archive_salary_component",
    "def restore_salary_component_archive",
    "def delete_unused_salary_component",
    "def archive_overtime_policy",
    "def restore_overtime_policy_archive",
    "def delete_unused_overtime_policy",
    "Restore the archived salary component before editing it.",
    "Restore the archived overtime policy before editing it.",
    "archived_at__isnull=True",
)
require(
    "apps/internal_payroll/services/payment.py",
    "def archive_bank_export_template",
    "def restore_bank_export_template_archive",
    "def delete_unused_bank_export_template",
    "def delete_unused_employee_payment_profile",
    "Restore the archived bank/WPS export template before editing it.",
    "not template.is_active or template.archived_at",
    "archived_at__isnull=True",
)
require(
    "apps/internal_payroll/salary_api.py",
    "def _configuration_status",
    'normalized == "archived"',
    "def salary_component_lifecycle_api",
    "def overtime_policy_lifecycle_api",
    '@require_http_methods(["PATCH", "DELETE"])',
)
require(
    "apps/internal_payroll/payment_api.py",
    "def bank_export_template_lifecycle_api",
    "delete_unused_employee_payment_profile",
    '@require_http_methods(["PATCH", "DELETE"])',
)
require(
    "apps/internal_payroll/selectors/salary.py",
    '"status": "Archived" if component.archived_at',
    '"status": "Archived" if policy.archived_at',
    '"archivedReason"',
)
require(
    "apps/internal_payroll/selectors/payment.py",
    '"status": "Archived" if template.archived_at',
    "not item.archived_at",
)
require(
    "static/payroll/js/app.js",
    "overtimePolicyStatus: 'Active'",
    "data-config-lifecycle",
    "function openConfigurationLifecycleDrawer",
    "Delete unused payment profile",
    "Archived templates remain visible for payment history",
    "item.active && !item.archived",
)
require(
    "apps/accounts/admin.py",
    'actions = ("activate_accounts", "deactivate_accounts")',
    "Deactivate identities instead of deleting them",
    'admin.site.site_header = "SESCCO MS Administration"',
)

migration = "apps/internal_payroll/migrations/0010_secondary_configuration_lifecycle.py"
parse(migration)
if migration not in text("merge/frozen-merge-migrations.sha256"):
    fail(f"{migration} is not frozen in merge/frozen-merge-migrations.sha256")

print("Secondary Payroll configuration lifecycle contract verified.")
