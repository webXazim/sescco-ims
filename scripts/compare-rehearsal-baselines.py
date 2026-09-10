#!/usr/bin/env python3
"""Compare pre/post migration row counts that the Payroll merge must preserve."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PRESERVED_MODELS = (
    "accounts.User",
    "projects.Project",
    "inventory.Unit",
    "inventory.Supplier",
    "inventory.InventoryLocation",
    "inventory.StockItem",
    "inventory.StockDocument",
    "inventory.StockMovement",
    "inventory.StockTransfer",
    "inventory.StockTransferLine",
    "data_exchange.ImportJob",
    "data_exchange.ImportRow",
    "data_exchange.ExportAudit",
    "explorer.SavedView",
    "explorer.TablePreference",
)


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()

    before = load(args.before).get("model_counts", {})
    after = load(args.after).get("model_counts", {})
    errors: list[str] = []

    for label in PRESERVED_MODELS:
        old = before.get(label)
        new = after.get(label)
        if old is None:
            errors.append(f"{label}: pre-migration count is unavailable")
        elif new is None:
            errors.append(f"{label}: post-migration count is unavailable")
        elif old != new:
            errors.append(f"{label}: row count changed {old} -> {new}")

    if errors:
        print("Migration preservation check FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 2

    print(f"Migration preservation check passed for {len(PRESERVED_MODELS)} legacy IMS models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
