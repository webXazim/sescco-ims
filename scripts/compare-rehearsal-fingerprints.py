#!/usr/bin/env python3
"""Compare pre/post legacy IMS data fingerprints from Upgrade 12 rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    before = load(args.before).get("tables", {})
    after = load(args.after).get("tables", {})
    errors: list[str] = []

    if set(before) != set(after):
        errors.append("protected table set changed")

    for table in sorted(set(before) & set(after)):
        old = before[table]
        new = after[table]
        if old.get("columns") != new.get("columns"):
            errors.append(f"{table}: protected column contract changed")
        if old.get("primary_key") != new.get("primary_key"):
            errors.append(f"{table}: primary-key ordering contract changed")
        if old.get("row_count") != new.get("row_count"):
            errors.append(
                f"{table}: row count changed {old.get('row_count')} -> {new.get('row_count')}"
            )
        if old.get("sha256") != new.get("sha256"):
            errors.append(f"{table}: legacy field data fingerprint changed")

    if errors:
        print("Legacy IMS data fingerprint check FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 2
    print(f"Legacy IMS data fingerprint check passed for {len(before)} protected tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
