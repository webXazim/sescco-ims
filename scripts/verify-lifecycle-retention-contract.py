#!/usr/bin/env python3
"""Production gate for SESCCO MS lifecycle/retention coverage."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "merge/lifecycle-retention-contract.json"


def fail(message: str) -> None:
    raise SystemExit(f"lifecycle retention verification failed: {message}")


def persisted_models() -> set[str]:
    result: set[str] = set()
    for app_dir in sorted((ROOT / "apps").iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("__"):
            continue
        candidates = []
        direct = app_dir / "models.py"
        if direct.is_file():
            candidates.append(direct)
        package = app_dir / "models"
        if package.is_dir():
            candidates.extend(sorted(p for p in package.glob("*.py") if p.name != "__init__.py"))
        for path in candidates:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = {ast.unparse(base) for base in node.bases}
                is_model = any(
                    base in {"models.Model", "CompanyOwnedModel", "UUIDTimeStampedModel", "AbstractUser"}
                    for base in bases
                )
                is_abstract = False
                for child in node.body:
                    if isinstance(child, ast.ClassDef) and child.name == "Meta":
                        for meta_item in child.body:
                            if (
                                isinstance(meta_item, ast.Assign)
                                and any(isinstance(target, ast.Name) and target.id == "abstract" for target in meta_item.targets)
                                and isinstance(meta_item.value, ast.Constant)
                                and meta_item.value.value is True
                            ):
                                is_abstract = True
                if is_model and not is_abstract:
                    result.add(f"{app_dir.name}.{node.name}")
    return result


data = json.loads(CONTRACT.read_text(encoding="utf-8"))
models = data.get("models")
if not isinstance(models, dict) or not models:
    fail("contract models mapping is missing")

allowed_modes = {
    "access_deactivate_only",
    "effective_dated_supersede_only",
    "employment_lifecycle_archive_delete_unused",
    "employment_lifecycle_archive_trash_30d",
    "immutable_finalized_document",
    "immutable_ledger",
    "immutable_snapshot",
    "import_staging_retention",
    "master_archive_delete_unused",
    "master_archive_trash_30d",
    "master_archive_trash_30d_reversible_cascade",
    "profile_delete_unused_or_deactivate",
    "system_singleton_no_delete",
    "user_preference_delete_ok",
    "worker_lifecycle_archive_delete_unused",
    "worker_lifecycle_archive_trash_30d",
    "workflow_record_no_delete",
}
for label, spec in models.items():
    mode = spec.get("mode") if isinstance(spec, dict) else None
    if mode not in allowed_modes:
        fail(f"{label} has unknown retention mode {mode!r}")

trash_modes = {
    "projects.Project": "master_archive_trash_30d_reversible_cascade",
    "internal_payroll.Branch": "master_archive_trash_30d_reversible_cascade",
    "internal_payroll.Department": "master_archive_trash_30d_reversible_cascade",
    "internal_payroll.InternalEmployee": "employment_lifecycle_archive_trash_30d",
    "rental_manpower.ManpowerSupplier": "master_archive_trash_30d_reversible_cascade",
    "rental_manpower.RentalWorker": "worker_lifecycle_archive_trash_30d",
}
for label, expected in trash_modes.items():
    if models.get(label, {}).get("mode") != expected:
        fail(f"{label} must use the 30-day Trash retention mode")

actual = persisted_models()
contracted = set(models)
missing = sorted(actual - contracted)
unknown = sorted(contracted - actual)
if missing:
    fail("persisted models without a retention classification: " + ", ".join(missing))
if unknown:
    fail("retention contract references missing models: " + ", ".join(unknown))

# Critical master records must stay on the central lifecycle policy registry.
policy_texts = "\n".join(
    (ROOT / path).read_text(encoding="utf-8")
    for path in (
        "apps/internal_payroll/lifecycle.py",
        "apps/rental_manpower/lifecycle.py",
        "apps/projects/lifecycle.py",
        "apps/inventory/lifecycle.py",
    )
)
for model_name in (
    "Branch", "Department", "InternalEmployee", "SalaryComponent", "OvertimePolicy", "BankExportTemplate",
    "ManpowerSupplier", "RentalWorker", "Project", "Unit", "Supplier", "InventoryLocation", "StockItem",
):
    if f"register_lifecycle_policy({model_name}," not in policy_texts:
        fail(f"{model_name} is not registered with the central lifecycle authority")

salary_api = (ROOT / "apps/internal_payroll/salary_api.py").read_text(encoding="utf-8")
if '@require_http_methods(["GET", "POST"])\n@api_workspace_required(Workspace.INTERNAL)\ndef salary_structures_api' not in salary_api:
    fail("salary structures must remain create/read effective-dated records; ordinary PATCH/DELETE is not allowed")

app_js = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
for needle in (
    "Create effective change",
    "Effective-dated history is retained",
    "Company policy is retained",
    "archive:{title:'Archive'}, trash:{title:'Delete'}",
    "Delete with 30-day recovery",
    "restore_trash",
):
    if needle not in app_js:
        fail(f"Payroll UI retention guidance is missing: {needle}")


cascade_sources = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (
    "apps/internal_payroll/selectors/organization.py",
    "apps/internal_payroll/services/attendance.py",
    "apps/rental_manpower/selectors/masters.py",
    "apps/rental_manpower/services/assignments.py",
    "apps/projects/services.py",
))
for needle in (
    "cascadeLifecycle",
    "operational_internal_employees",
    "Inherited from archived supplier",
    "archive_previous_status",
    "cascade_scope",
):
    if needle not in cascade_sources:
        fail(f"reversible parent lifecycle cascade is missing {needle!r}")


trash_source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (
    "apps/core/trash.py",
    "apps/internal_payroll/models/organization.py",
    "apps/rental_manpower/models/masters.py",
    "apps/projects/models.py",
    "apps/inventory/management/commands/purge_trash.py",
))
for needle in ("TRASH_RETENTION_DAYS = 30", "deleted_at", "purge_after", "deletion_reason", "move_to_trash", "restore_from_trash"):
    if needle not in trash_source:
        fail(f"30-day Trash implementation is missing {needle!r}")

purge_text = (ROOT / "apps/inventory/management/commands/purge_trash.py").read_text(encoding="utf-8")
for needle in (
    "Collector",
    "_hard_delete_is_history_safe",
    "collector.fast_deletes",
    "purge_after=None",
    "protected historical tombstones",
):
    if needle not in purge_text:
        fail(f"Trash expiry must preserve related history; purge safety is missing {needle!r}")

settings_text = (ROOT / "config/settings/base.py").read_text(encoding="utf-8")
if 'APP_NAME = "SESCCO MS"' not in settings_text:
    fail("product branding must be locked to SESCCO MS")

print(f"Lifecycle retention contract verified for {len(actual)} persisted SESCCO models.")
