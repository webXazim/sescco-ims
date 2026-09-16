#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.117"
MIGRATION = "apps/sourcing/migrations/0008_align_abstract_relation_state.py"
EXPECTED_COMPANY_MODELS = {
    "sourcingmanpowercontact",
    "sourcingmanpowersupplier",
    "sourcingmaterial",
    "sourcingsettings",
    "sourcingtrade",
    "sourcingvendor",
    "sourcingvendorcontact",
    "sourcingvendoroffer",
    "sourcingvendorofferrevision",
    "sourcingworkforceoffer",
    "sourcingworkforceofferrevision",
}
EXPECTED_DELETED_BY_MODELS = {"sourcingmanpowersupplier", "sourcingvendor"}


def fail(message: str) -> None:
    raise SystemExit(f"SOURCING MIGRATION STATE HOTFIX ERROR: {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


if read("VERSION").strip() != VERSION:
    fail(f"VERSION must be {VERSION}")

contract = json.loads(read("merge/sourcing-migration-state-hotfix.json"))
if contract.get("release") != VERSION or contract.get("scope") != "sourcing-migration-state-drift-hotfix":
    fail("hotfix contract identity mismatch")
if contract.get("previous_archive_sha256") != "5a3c71f2b0fb1cc065beaadc5ec6eb8846d8834bf12389de55e78f37dc7d9fdb":
    fail("1.0.112 predecessor checksum changed")
if contract.get("alter_field_operations") != 13:
    fail("hotfix must contain exactly 13 AlterField operations")
for key in (
    "database_data_change",
    "database_column_change",
    "database_index_change",
    "payroll_formula_change",
    "inventory_quantity_change",
    "permission_catalog_change",
    "sourcing_business_rule_change",
):
    if contract.get(key) is not False:
        fail(f"{key} must remain false")

base = read("apps/core/models/scoping.py")
if 'related_name="%(app_label)s_%(class)s_records"' not in base:
    fail("CompanyOwnedModel placeholder related_name changed")
sourcing_base = read("apps/sourcing/models/base.py")
if 'related_name="%(app_label)s_%(class)s_deleted_records"' not in sourcing_base:
    fail("SourcingLifecycleModel deleted_by placeholder related_name changed")

text = read(MIGRATION)
ast.parse(text, filename=MIGRATION)
tree = ast.parse(text, filename=MIGRATION)
company_models = set()
deleted_by_models = set()
alter_count = 0
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "AlterField"):
        continue
    alter_count += 1
    kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
    model_node = kwargs.get("model_name")
    name_node = kwargs.get("name")
    if not (isinstance(model_node, ast.Constant) and isinstance(name_node, ast.Constant)):
        fail("AlterField must use literal model_name/name")
    model_name = model_node.value
    field_name = name_node.value
    segment = ast.get_source_segment(text, node) or ""
    if field_name == "company":
        company_models.add(model_name)
        if 'related_name="%(app_label)s_%(class)s_records"' not in segment:
            fail(f"company state alignment missing placeholder related_name: {model_name}")
        if "deletion.PROTECT" not in segment or 'to="core.company"' not in segment:
            fail(f"company state alignment changed database semantics: {model_name}")
    elif field_name == "deleted_by":
        deleted_by_models.add(model_name)
        if 'related_name="%(app_label)s_%(class)s_deleted_records"' not in segment:
            fail(f"deleted_by state alignment missing placeholder related_name: {model_name}")
        if "deletion.SET_NULL" not in segment or "null=True" not in segment or "blank=True" not in segment:
            fail(f"deleted_by state alignment changed lifecycle semantics: {model_name}")
    else:
        fail(f"unexpected field in migration-state hotfix: {model_name}.{field_name}")

if alter_count != 13:
    fail(f"expected 13 AlterField operations, found {alter_count}")
if company_models != EXPECTED_COMPANY_MODELS:
    fail(f"company relation state set mismatch: {sorted(company_models ^ EXPECTED_COMPANY_MODELS)}")
if deleted_by_models != EXPECTED_DELETED_BY_MODELS:
    fail(f"deleted_by relation state set mismatch: {sorted(deleted_by_models ^ EXPECTED_DELETED_BY_MODELS)}")

release = json.loads(read("merge/release-candidate.json"))
if release.get("release") != VERSION:
    fail("release candidate does not match VERSION")
if "scripts/verify-sourcing-migration-state-hotfix.py" not in set(release.get("required_static_gates") or []):
    fail("release candidate does not require migration-state verifier")
if "python manage.py makemigrations --check --dry-run" not in set(release.get("required_runtime_gates") or []):
    fail("authoritative makemigrations drift check is not required")

print("Verified SESCCO MS 1.0.117 Sourcing migration-state drift hotfix: 11 company relations + 2 deleted_by relations aligned without data/column/index changes.")
