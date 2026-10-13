#!/usr/bin/env python3
"""Structural Upgrade 03 checks, not a substitute for Django runtime certification."""
from pathlib import Path
import ast
import re

root = Path(__file__).resolve().parents[1]

def text(path):
    return (root / path).read_text(encoding="utf-8")

def insist(cond, label):
    if not cond:
        raise SystemExit(f"UPGRADE 03 ERROR: {label}")

p = text("apps/accounts/access_catalog.py")
for name in ("SOURCING_SUBCONTRACTORS_VIEW", "SOURCING_SUBCONTRACTORS_MANAGE"):
    insist(name in p, f"missing {name} permission")
mp = text("apps/accounts/migrations/0013_subcontractor_sourcing_authority.py")
for literal in ("RemoveConstraint", "AddConstraint", "grant_company_owner", "sourcing.subcontractors.view", "sourcing.subcontractors.manage"):
    insist(literal in mp, f"missing access schema migration {literal}")
insist("SOURCING_SUBCONTRACTORS_MANAGE.value: AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value" in text("apps/accounts/access_profiles.py"), "manage requires view")
source = text("apps/sourcing/services/subcontractors.py")
selector = text("apps/sourcing/selectors/subcontractors.py")
views = text("apps/sourcing/views.py")
urls = text("apps/sourcing/urls.py")
for py in ("apps/sourcing/services/subcontractors.py", "apps/sourcing/selectors/subcontractors.py", "apps/sourcing/tests/test_subcontractor_directory.py", "apps/accounts/migrations/0013_subcontractor_sourcing_authority.py"):
    ast.parse(text(py), filename=py)
for forbidden in ("apps.inventory", "apps.rental_manpower", "apps.internal_payroll", "apps.projects", "apps.accounting"):
    insist(forbidden not in source + selector, f"operational coupling {forbidden}")
for label in ("create_subcontractor", "update_subcontractor", "archive_subcontractor", "trash_subcontractor", "delete_subcontractor", "create_subcontractor_contact", "update_subcontractor_contact", "deactivate_subcontractor_contact"):
    insist(f"def {label}(" in source, f"missing service {label}")
for label in ("subcontractor_list", "subcontractor_create", "subcontractor_detail", "subcontractor_edit", "subcontractor_delete", "subcontractor_contact_create", "subcontractor_contact_edit"):
    insist(f"def {label}(" in views, f"missing view {label}")
    insist(f'name="{label}"' in urls, f"missing route {label}")
insist("_require_subcontractor_view(request)" in views and "_require_subcontractor_manage(request)" in views, "missing view/manage access guards")
insist("for_company(company)" in selector and "for_company(actor_membership.company)" in source, "missing company isolation")
for t in ("list.html", "detail.html", "form.html", "contact_form.html"):
    insist((root / "templates/sourcing/subcontractors" / t).exists(), f"missing {t}")
insist("SOURCING_ACCESS.subcontractors.view" in text("templates/sourcing/sidebar.html"), "missing permission-filtered navigation")
insist("apps.sourcing.tests.test_subcontractor_directory" in text("scripts/release-tasks.sh"), "missing release test target")
print("PASS: Upgrade 03 structural isolation, independent permission wiring, contacts, views, routes, and templates.")
