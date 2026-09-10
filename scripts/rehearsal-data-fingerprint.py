#!/usr/bin/env python3
"""Emit stable fingerprints of legacy IMS table data for migration rehearsal.

Run inside the pinned Django image against PostgreSQL. With --column-contract,
only the pre-migration columns recorded in that snapshot are hashed, so additive
Upgrade 2-12 columns do not create false differences.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

PROTECTED_TABLES = (
    "accounts_user",
    "accounts_user_groups",
    "accounts_user_user_permissions",
    "projects_project",
    "inventory_unit",
    "inventory_supplier",
    "inventory_inventorylocation",
    "inventory_stockitem",
    "inventory_stockdocument",
    "inventory_stockmovement",
    "inventory_stocktransfer",
    "inventory_stocktransferline",
    "data_exchange_importjob",
    "data_exchange_importrow",
    "data_exchange_exportaudit",
    "explorer_savedview",
    "explorer_tablepreference",
)


def primary_key_columns(cursor, table: str) -> list[str]:
    constraints = connection.introspection.get_constraints(cursor, table)
    for details in constraints.values():
        if details.get("primary_key"):
            return list(details.get("columns") or [])
    return []


def snapshot(contract: dict | None = None) -> dict:
    quote = connection.ops.quote_name
    existing = set(connection.introspection.table_names())
    output: dict[str, object] = {
        "database_vendor": connection.vendor,
        "format": 1,
        "tables": {},
    }
    tables: dict[str, object] = output["tables"]  # type: ignore[assignment]

    with connection.cursor() as cursor:
        for table in PROTECTED_TABLES:
            if table not in existing:
                raise RuntimeError(f"Protected legacy table is missing: {table}")
            description = connection.introspection.get_table_description(cursor, table)
            actual_columns = [column.name for column in description]

            if contract:
                baseline = contract.get("tables", {}).get(table)
                if not baseline:
                    raise RuntimeError(f"Column contract is missing protected table: {table}")
                columns = list(baseline["columns"])
                missing = [column for column in columns if column not in actual_columns]
                if missing:
                    raise RuntimeError(f"{table} lost baseline columns: {', '.join(missing)}")
                pk_columns = list(baseline["primary_key"])
            else:
                columns = actual_columns
                pk_columns = primary_key_columns(cursor, table)

            if not pk_columns:
                raise RuntimeError(f"Protected table has no primary key ordering contract: {table}")
            if any(column not in columns for column in pk_columns):
                raise RuntimeError(f"Primary key is outside the protected column set for {table}")

            selected = ", ".join(quote(column) for column in columns)
            ordered = ", ".join(quote(column) for column in pk_columns)
            sql = (
                f"SELECT row_to_json(snapshot_row)::text FROM "
                f"(SELECT {selected} FROM {quote(table)} ORDER BY {ordered}) AS snapshot_row"
            )
            cursor.execute(sql)
            digest = hashlib.sha256()
            row_count = 0
            for (row_json,) in cursor:
                digest.update(row_json.encode("utf-8"))
                digest.update(b"\n")
                row_count += 1

            tables[table] = {
                "columns": columns,
                "primary_key": pk_columns,
                "row_count": row_count,
                "sha256": digest.hexdigest(),
            }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--column-contract",
        type=Path,
        help="Pre-migration snapshot whose exact columns must be hashed.",
    )
    args = parser.parse_args()
    contract = None
    if args.column_contract:
        contract = json.loads(args.column_contract.read_text(encoding="utf-8"))
    print(json.dumps(snapshot(contract), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
