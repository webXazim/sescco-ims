#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"EMPLOYEE LIFECYCLE ERROR: {message}")


def require(rel: str, text: str) -> None:
    value = (ROOT / rel).read_text(encoding="utf-8")
    if text not in value:
        fail(f"{rel} is missing lifecycle contract: {text}")


for rel in (
    "apps/internal_payroll/models/organization.py",
    "apps/internal_payroll/services/organization.py",
    "apps/internal_payroll/lifecycle.py",
    "apps/internal_payroll/selectors/organization.py",
    "apps/internal_payroll/api.py",
    "apps/internal_payroll/urls.py",
    "apps/internal_payroll/migrations/0008_employee_lifecycle_archive.py",
    "apps/internal_payroll/migrations/0011_master_trash_retention.py",
    "static/payroll/js/app.js",
):
    ast.parse((ROOT / rel).read_text(encoding="utf-8")) if rel.endswith(".py") else None

for rel, text in [
    ("apps/internal_payroll/models/organization.py", "archived_at = models.DateTimeField"),
    ("apps/internal_payroll/models/organization.py", "internal_employee_archive_requires_stopped_status"),
    ("apps/internal_payroll/migrations/0008_employee_lifecycle_archive.py", "close_existing_terminated_assignments"),
    ("apps/internal_payroll/services/organization.py", "def change_employee_lifecycle("),
    ("apps/internal_payroll/services/organization.py", "def archive_employee("),
    ("apps/internal_payroll/services/organization.py", "def restore_employee_archive("),
    ("apps/internal_payroll/services/organization.py", "def delete_unused_employee("),
    ("apps/internal_payroll/lifecycle.py", "Deactivate or terminate the employee before moving the record to Trash."),
    ("apps/internal_payroll/services/organization.py", "require_lifecycle_action("),
    ("apps/internal_payroll/services/organization.py", "record_lifecycle_action("),
    ("apps/internal_payroll/api.py", "def employee_lifecycle_api("),
    ("apps/internal_payroll/api.py", 'Use the employee lifecycle action to change employment status.'),
    ("apps/internal_payroll/urls.py", 'name="employee-lifecycle-api"'),
    ("apps/internal_payroll/selectors/organization.py", '"archived": employee.archived_at is not None'),
    ("static/payroll/js/app.js", "function employeeLifecycleActions(employee)"),
    ("static/payroll/js/app.js", "Deactivate / stop payroll eligibility"),
    ("static/payroll/js/app.js", "Terminate employment"),
    ("static/payroll/js/app.js", "Archive employee"),
    ("static/payroll/js/app.js", "Move to Trash"),
    ("static/payroll/js/app.js", "employee-record-confirmation"),
    ("static/payroll/js/app.js", "employee-profile-page ui-v2-prs-internal-page"),
    ("static/payroll/css/v2/payroll-controls.css", "padding: 16px 18px !important;"),
    ("templates/payroll/app.html", "payroll/css/v2/payroll-controls.css' %}?v=1.0.39"),
    ("templates/payroll/app.html", "payroll/js/app.js' %}?v=1.0.39"),
]:
    require(rel, text)

frontend = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
edit_start = frontend.find("function openEmployeeEditDrawer")
life_start = frontend.find("function openEmployeeLifecycleDrawer")
if edit_start < 0 or life_start < 0 or life_start <= edit_start:
    fail("employee edit/lifecycle drawer boundary is missing")
edit_block = frontend[edit_start:life_start]
for forbidden in ("employee-status", "employee-end-date"):
    if forbidden in edit_block:
        fail(f"normal employee Edit drawer still owns protected lifecycle field {forbidden}")

migration_manifest = (ROOT / "merge/frozen-merge-migrations.sha256").read_text(encoding="utf-8")
for migration in ("apps/internal_payroll/migrations/0008_employee_lifecycle_archive.py", "apps/internal_payroll/migrations/0011_master_trash_retention.py"):
    if migration not in migration_manifest:
        fail(f"employee lifecycle migration is not frozen: {migration}")

print("Internal employee lifecycle, separate Archive/30-day Trash, and profile-padding contract verified.")
