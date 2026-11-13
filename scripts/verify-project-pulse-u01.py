#!/usr/bin/env python3
"""Dependency-free static integrity checks for U01; not a Django runtime test."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file(name):
    return (ROOT / name).read_text(encoding="utf8")


def assert_contains(path, phrase):
    assert phrase in file(path), f"Expected {phrase!r} in {path}"


for path in list((ROOT / "apps").rglob("*.py")) + list((ROOT / "config").rglob("*.py")):
    ast.parse(path.read_text(encoding="utf8"), filename=str(path))

catalog = file("apps/accounts/access_catalog.py")
section = catalog.split("class AccessPermission(StrEnum):", 1)[1].split("_PERMISSION_LABELS:", 1)[0]
values = re.findall(r'^\s+[A-Z][A-Z0-9_]+\s*=\s*"([^\"]+)"', section, flags=re.M)
assert len(values) == len(set(values)), "Duplicate permissions"
assert {"pulse.overview.view", "pulse.projects.view"}.issubset(values)
ns = {}
migration = ROOT / "apps/accounts/migrations/0017_project_pulse_u01_authority.py"
node = ast.parse(migration.read_text())
perm_assign = next(n for n in node.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ALL_PERMISSIONS' for t in n.targets))
migration_perms = ast.literal_eval(perm_assign.value)
assert set(values) == set(migration_perms), 'Migration/database constraint does not match access catalog'
assert_contains("apps/accounts/modules.py", 'PROJECT_PULSE = "project_pulse"')
assert_contains("apps/accounts/modules.py", 'return membership_has_permission(membership, AccessPermission.PULSE_OVERVIEW_VIEW)')
assert_contains("apps/accounts/context.py", '"key": PlatformModule.PROJECT_PULSE.value')
assert_contains("apps/accounts/access_profiles.py", '"pulse": "Project Pulse"')
assert_contains("apps/accounts/access_profiles.py", 'AccessPermission.PULSE_PROJECTS_VIEW.value: AccessPermission.PULSE_OVERVIEW_VIEW.value')
assert_contains("config/settings/base.py", 'apps.project_pulse.apps.ProjectPulseConfig')
assert_contains("config/urls.py", '"app/project-pulse/"')
assert_contains("templates/partials/platform_switchers.html", "current_module == 'project_pulse'")
for path in ('base.html', 'sidebar.html', 'home.html', 'project_list.html', 'project_detail.html'):
    assert (ROOT / 'templates/project_pulse' / path).is_file(), path
assert (ROOT / 'static/project_pulse/css/project-pulse.css').is_file()
view = file('apps/project_pulse/views.py')
assert view.count('@login_required') == 3 and view.count('@require_GET') == 3
assert 'get_object_or_404(projects' in view
assert 'scoped_projects(request)' in view
access = file('apps/project_pulse/access.py')
assert 'restrict_projects(' in access and 'Project.objects.for_company(request.company)' in access
assert 'inventory.models' not in view + access and 'internal_payroll.models' not in view + access
print(f"PASS: Project Pulse U01 static checks; {len(values)} access permissions, 3 scoped pages, 5 templates")
