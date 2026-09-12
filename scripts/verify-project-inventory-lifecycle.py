#!/usr/bin/env python3
"""Static release contract for SESCCO MS project + Inventory master lifecycle."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"project/inventory lifecycle verification failed: {message}")


def text(path: str) -> str:
    p = ROOT / path
    if not p.is_file():
        fail(f"missing {path}")
    return p.read_text(encoding="utf-8")


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
    "apps/projects/lifecycle.py",
    "apps/projects/services.py",
    "apps/projects/models.py",
    "apps/inventory/lifecycle.py",
    "apps/inventory/services/lifecycle.py",
    "apps/inventory/models.py",
    "apps/inventory/services/stock.py",
    "apps/inventory/services/transfers.py",
    "apps/inventory/signals.py",
):
    parse(path)

require(
    "apps/projects/lifecycle.py",
    "class ProjectLifecyclePolicy",
    "LifecycleAction.ARCHIVE",
    "LifecycleAction.RESTORE",
    "LifecycleAction.DELETE",
    '"quantity_bearing_stock"',
    '"open_rental_assignments"',
)
require(
    "apps/projects/services.py",
    "def archive_project",
    "def restore_project_archive",
    "def trash_unused_project",
    "def restore_project_trash",
    "archive_previous_status",
    '"cascade_scope": "project_operations"',
    '"retention_days": 30',
    "deleted_at=cascade_deleted_at, purge_after=cascade_purge_after",
)
require(
    "apps/projects/models.py",
    "archived_at = models.DateTimeField",
    "archived_reason = models.TextField",
    "archive_previous_status = models.CharField",
    "Set the actual end date before completing the project.",
    "Release or transfer open rental manpower assignments before completing the project.",
)
require(
    "apps/projects/views.py",
    '"archive":',
    '"complete": Project.Status.COMPLETED',
    '"reactivate": Project.Status.ACTIVE',
    "trash_unused_project",
)
require(
    "apps/projects/forms.py",
    '"end_date",',
)
if '"status"' in text("apps/projects/forms.py"):
    fail("ProjectForm must not expose status as an ordinary editable field")

require(
    "apps/inventory/lifecycle.py",
    "class UnitLifecyclePolicy",
    "class SupplierLifecyclePolicy",
    "class StockItemLifecyclePolicy",
    "class InventoryLocationLifecyclePolicy",
    "project_managed_location",
    "historical_records_exist",
)
require(
    "apps/inventory/services/lifecycle.py",
    "def archive_unit",
    "def restore_unit",
    "def trash_unused_unit",
    "def archive_supplier",
    "def restore_supplier",
    "def trash_unused_supplier",
    "def archive_stock_item",
    "def restore_stock_item",
    "def trash_unused_stock_item",
    "def archive_location",
    "def restore_location",
    "def trash_unused_location",
    '"retention_days": 30',
)
require(
    "apps/inventory/services/stock.py",
    "supplier_master.archived_at",
    "Restore the supplier before using it for new stock activity.",
    "unit.archived_at",
)
require(
    "apps/inventory/services/transfers.py",
    "Matching destination stock is archived. Restore",
)
require(
    "apps/inventory/signals.py",
    "archived_at",
    "archived_reason",
    "instance.status == Project.Status.ACTIVE",
)
require(
    "apps/inventory/forms.py",
    "archived_at__isnull=True",
    "deleted_at__isnull=True",
)
require(
    "apps/inventory/views.py",
    "office_locations",
    "InventoryLocationListView",
    "UnitStatusView",
    "SupplierStatusView",
    "StockItemStatusView",
    "InventoryLocationStatusView",
)
require("templates/partials/sidebar.html", "inventory:locations", "Locations")
require("templates/inventory/archive_list.html", "Locations")
require("templates/inventory/location_list.html", "Archived", "Delete unused")
require("templates/inventory/office_inventory.html", "office_locations")
require("templates/projects/project_detail.html", "Archive", "Move to Trash for 30 days")

for migration in (
    "apps/projects/migrations/0005_project_archive_metadata.py",
    "apps/projects/migrations/0006_project_reversible_archive_state.py",
    "apps/inventory/migrations/0014_inventory_master_lifecycle.py",
):
    parse(migration)
    manifest = text("merge/frozen-merge-migrations.sha256")
    if migration not in manifest:
        fail(f"{migration} is not frozen in merge/frozen-merge-migrations.sha256")

require(
    "apps/inventory/management/commands/purge_trash.py",
    "InventoryLocation",
)
require(
    "apps/core/context_processors.py",
    "archived_at__isnull=False",
    "InventoryLocation",
)

print("Project reversible cascade + Inventory master lifecycle contract verified.")
