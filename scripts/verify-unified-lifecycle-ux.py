#!/usr/bin/env python3
"""Static release contract for SESCCO MS unified lifecycle UX."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"unified lifecycle UX verification failed: {message}")


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


require(
    "static/payroll/css/v2/index.css",
    '@import "./components/lifecycle.css";',
)
require(
    "static/payroll/css/v2/components/lifecycle.css",
    ".ui-v2-lifecycle-menu",
    ".ui-v2-lifecycle-panel",
    ".ui-v2-lifecycle-error",
    ".is-lifecycle-danger",
)
require(
    "static/platform/css/lifecycle-actions.css",
    ".lifecycle-actions",
    ".lifecycle-policy-note",
    ".row-action-danger",
)
require(
    "templates/base.html",
    "platform/css/lifecycle-actions.css",
    "?v=1.0.39",
)
require(
    "static/payroll/js/app.js",
    "function lifecycleMenuItem",
    "function lifecycleActionsMenu",
    "function lifecycleDrawerIntro",
    "function showLifecycleDrawerError",
    "data-lifecycle-menu-action",
    "payrollDropdownDelegation",
    "event.target.closest('[data-dropdown-trigger]')",
    "organization-lifecycle",
    "rental-master-lifecycle",
    "configuration-lifecycle",
    "Delete with 30-day recovery",
    "archive:{title:'Archive'}, trash:{title:'Delete'}",
    "const title = isTrash ? 'Delete' : 'Archive';",
    "Delete unused payment profile",
    "is-lifecycle-danger",
)


require(
    "static/payroll/css/v2/payroll-controls.css",
    "1.0.40 — lifecycle Actions menu visibility",
    ".ui-v2-payroll-master-detail {",
    "overflow: visible;",
    ".ui-v2-payroll-master-detail__actions .ui-v2-lifecycle-menu > .ui-v2-prs-dropdown-menu",
    "bottom: calc(100% + 7px);",
)

# Lifecycle navigation must use the concise user-facing labels requested for the
# private SESCCO MS shell. Internal route/storage names may remain unchanged.
app = text("static/payroll/js/app.js")
for forbidden in ("Archive Bin", "Trash Bin", "Move to Trash"):
    if forbidden in app:
        fail(f"Payroll lifecycle UI still exposes legacy label: {forbidden}")

# The drawer save gate must explicitly permit every lifecycle drawer type.
app = text("static/payroll/js/app.js")
for drawer_type in ("organization-lifecycle", "rental-master-lifecycle", "employee-record-lifecycle", "project-lifecycle", "configuration-lifecycle"):
    if f"'{drawer_type}'" not in app:
        fail(f"saveDrawer lifecycle allowlist is missing {drawer_type}")

# Core Payroll master screens must converge on the shared action menu rather than
# restoring one-off archive/delete button clusters.
for marker in (
    "Edit branch / office",
    "Archive branch / office",
    "Edit department",
    "Archive department",
    "Manage supplier status",
    "Manage worker status",
    "Archive employee",
    "Archive project",
    "Archive component",
    "Archive policy",
    "Archive template",
):
    if marker not in app:
        fail(f"Payroll lifecycle action surface is missing: {marker}")

for template in (
    "templates/projects/project_detail.html",
    "templates/inventory/stockitem_detail.html",
    "templates/inventory/unit_form.html",
    "templates/inventory/supplier_form.html",
    "templates/inventory/location_list.html",
):
    require(template, "row-actions lifecycle-actions")

require(
    "templates/projects/project_detail.html",
    "<span>Delete</span><small>Move to Trash for 30 days; protected history remains intact</small>",
    "Archive project",
    "Restore from archive",
)
require(
    "templates/inventory/stockitem_detail.html",
    "Delete unused record",
    "Archive preserves real Inventory history",
)
require(
    "templates/inventory/unit_form.html",
    "Delete unused unit",
    "Archive unit",
)
require(
    "templates/inventory/supplier_form.html",
    "Delete unused supplier",
    "Archive supplier",
)
require(
    "templates/inventory/location_list.html",
    "Delete unused location",
    "Archive location",
)

# Delete remains visually and semantically separated as the destructive fallback.
for template in (
    "templates/projects/project_detail.html",
    "templates/inventory/stockitem_detail.html",
    "templates/inventory/unit_form.html",
    "templates/inventory/supplier_form.html",
    "templates/inventory/location_list.html",
):
    if "row-action-danger" not in text(template):
        fail(f"{template} does not mark delete-unused as destructive")

print("Unified lifecycle UX contract verified.")
