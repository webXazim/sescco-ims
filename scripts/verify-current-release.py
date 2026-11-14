#!/usr/bin/env python3
"""Current-release source and authorization checks for SESCCO IMS v1.0.128.

Historical merge/release verifier scripts and manifests are immutable baseline
artifacts for 1.0.117. This verifier checks the actual upgrade in its current
state, rather than falsely requiring the historical version and 97 permissions.
Must be combined with verify-merge-baseline.sh and Django runtime checks.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.128"
HISTORIC = "1.0.117"


def fail(message: str) -> None:
    raise SystemExit(f"CURRENT RELEASE ERROR: {message}")


def read(path: str) -> str:
    file = ROOT / path
    if not file.is_file():
        fail(f"missing required file: {path}")
    return file.read_text(encoding="utf-8")


def check() -> None:
    if read("VERSION").strip() != VERSION:
        fail(f"VERSION must match current release {VERSION}")
    if f"APP_VERSION={VERSION}" not in read(".env.production.example"):
        fail("Production environment template has a mismatched application version")
    # Preserve historical release-candidate identity, not overwrite its release
    # or frozen hashes whenever a new application module is added.
    prior = json.loads(read("merge/release-candidate.json"))
    if prior.get("release") != HISTORIC or prior.get("feature_freeze") is not True:
        fail("Legacy 1.0.117 release-candidate provenance changed")
    if prior.get("deployment_entrypoint") != "scripts/deploy-production.sh":
        fail("Canonical deployment entrypoint changed")
    for script in (
        "scripts/verify-release-candidate.py",
        "scripts/verify-granular-access-authority.py",
        "scripts/verify-single-access-authority.py",
    ):
        if HISTORIC not in read(script):
            fail(f"Historical baseline verifier unexpectedly modified: {script}")
    # The active catalog must agree exactly with the latest DB check constraint,
    # including all new Project Pulse grants. No role can silently gain grants
    # that the database/access-profile authority does not know about.
    c = ast.parse(read("apps/accounts/access_catalog.py"))
    enum = next((n for n in c.body if isinstance(n, ast.ClassDef) and n.name == "AccessPermission"), None)
    if enum is None:
        fail("Missing AccessPermission enum")
    codes = [n.value.value for n in enum.body if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
    if len(codes) != len(set(codes)) or len(codes) != 124:
        fail(f"Access catalog must contain 124 unique v1.0.128 permissions, found {len(codes)}")
    pulse = {x for x in codes if x.startswith("pulse.")}
    if len(pulse) != 27:
        fail(f"Project Pulse requires 27 explicit permissions, found {len(pulse)}")
    essential = {
        "access.profiles.manage", "inventory.stock.approve",
        "pulse.projects.view", "pulse.team.manage", "pulse.tasks.manage",
        "pulse.progress.update", "pulse.expenses.view", "pulse.expenses.approve",
        "pulse.budgets.view", "pulse.budgets.approve",
        "pulse.financials.view", "pulse.reports.export",
    }
    if essential - set(codes):
        fail(f"Critical permissions missing: {sorted(essential-set(codes))}")
    m = ast.parse(read("apps/accounts/migrations/0025_project_pulse_u09_report_authority.py"))
    assignments = [n.value for n in m.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "ALL_PERMISSIONS" for t in n.targets)]
    if len(assignments) != 1 or set(codes) != set(ast.literal_eval(assignments[0])):
        fail("Active permission catalog does not match latest database constraint migration")
    # Protect independently-scoped project records, receipt privacy, and the
    # deployment's actual service/data boundaries.
    for file, must_contain in {
        "config/settings/base.py": ["apps.project_pulse.apps.ProjectPulseConfig", 'AUTH_USER_MODEL = "accounts.User"'],
        "config/urls.py": ['"app/project-pulse/"'],
        "apps/accounts/modules.py": ['PROJECT_PULSE = "project_pulse"'],
        "docker-compose.yml": ["name: ims_pulse_private_data", "- ims_pulse_private_data:/app/private_uploads"],
        "scripts/backup.sh": ["pulse_private"],
        "scripts/restore.sh": ["pulse_private"],
        "scripts/deploy-production.sh": ["scripts/verify-production-freeze.sh", "scripts/release-tasks.sh"],
        "scripts/release-tasks.sh": ["run_manage test apps.project_pulse --noinput", "merge_access_report --fail-on-errors", "migrate --check"],
        "nginx/default.conf": ["location /media/", "return 404;"],
    }.items():
        content = read(file)
        for needle in must_contain:
            if needle not in content:
                fail(f"{file} missing required gate/marker: {needle}")
    # Do not permit accidental removal of U01-U08 schema or access migrations.
    for number in range(1, 8):
        if not list((ROOT / "apps/project_pulse/migrations").glob(f"{number:04d}_*.py")):
            fail(f"Missing Project Pulse migration {number:04d}")
    for number in range(17, 26):
        if not list((ROOT / "apps/accounts/migrations").glob(f"{number:04d}_*.py")):
            fail(f"Missing access authority migration {number:04d}")
    for file in (ROOT / "apps/project_pulse").rglob("*.py"):
        ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
    for file in (ROOT / "apps/accounts").rglob("*.py"):
        ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
    # Fail closed if the canonical UI reintroduces old cache tags.
    payroll = read("templates/payroll/app.html")
    for asset in ("payroll-controls.css", "payroll/js/app.js"):
        if f"{asset}' %}}?v={VERSION}" not in payroll:
            fail(f"Current-version cache tag missing for {asset}")
    print(f"Current SESCCO release {VERSION} validated: {len(codes)} permissions, "
          f"{len(pulse)} Project Pulse permissions, migrated authority, deployment boundaries.")


if __name__ == "__main__":
    check()
