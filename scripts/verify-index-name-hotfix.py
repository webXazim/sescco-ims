#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.116"
MAX_INDEX_NAME = 30
EXPECTED = {
    "apps/accounts/models.py": "acct_prof_company_active_idx",
    "apps/sourcing/models/manpower.py": "src_mpc_supplier_active_idx",
}
FORBIDDEN_CURRENT = {
    "apps/accounts/models.py": "acct_profile_company_active_idx",
    "apps/sourcing/models/manpower.py": "src_mpcontact_supplier_active_idx",
}
MIGRATIONS = {
    "apps/accounts/migrations/0013_rename_access_profile_index.py": (
        "acct_profile_company_active_idx", "acct_prof_company_active_idx"
    ),
    "apps/sourcing/migrations/0007_rename_manpower_contact_index.py": (
        "src_mpcontact_supplier_active_idx", "src_mpc_supplier_active_idx"
    ),
}


def fail(message: str) -> None:
    raise SystemExit(f"INDEX NAME HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        fail(f"missing file: {rel}")
    return p.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read("merge/index-name-deployment-hotfix.json"))
if contract.get("release") != VERSION or contract.get("scope") != "django-index-name-deployment-hotfix":
    fail("hotfix contract identity mismatch")

for rel, expected in EXPECTED.items():
    text = read(rel)
    if expected not in text:
        fail(f"new index name missing from {rel}: {expected}")
    if len(expected) > MAX_INDEX_NAME:
        fail(f"new index name remains too long: {expected}")
    old = FORBIDDEN_CURRENT[rel]
    # Historical migrations may retain the old name, but current model declarations may not.
    if old in text:
        fail(f"old overlength index name remains in current model: {old}")

for rel, (old, new) in MIGRATIONS.items():
    text = read(rel)
    if "migrations.RenameIndex" not in text or f'old_name="{old}"' not in text or f'new_name="{new}"' not in text:
        fail(f"forward RenameIndex contract incomplete: {rel}")
    ast.parse(text, filename=rel)

# Scan current model declarations only; historical migrations intentionally preserve old names.
for rel in ("apps/accounts/models.py", "apps/sourcing/models/manpower.py"):
    tree = ast.parse(read(rel), filename=rel)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "Index"):
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                if len(kw.value.value) > MAX_INDEX_NAME:
                    fail(f"Django E034 candidate remains in {rel}: {kw.value.value} ({len(kw.value.value)})")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION:
    fail("release candidate does not match current VERSION")
if contract.get("schema_change") is not True:
    fail("carried index hotfix contract must retain its RenameIndex schema-change declaration")
if "scripts/verify-index-name-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not require this hotfix verifier")
if "python manage.py check --deploy --fail-level ERROR" not in set(release.get("required_runtime_gates") or []):
    fail("authoritative Django deployment check is not required")

print("Verified SESCCO MS 1.0.116 Django index-name deployment hotfix.")
