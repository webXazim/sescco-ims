# Project Pulse — Upgrade 5/5: release hardening and verification

Base: `Project_Pulse_Upgrade_4_of_5_Full_Source.zip`. The **full-source archive includes Upgrades 1–5**. Use the patch only on an existing Upgrade 4 installation.

## Implementation finalized

- One `.xlsx` worksheet per selected project, using category-heading rows and the five fields `SN | Description | Unit | Quantity | % Completion`.
- **Blank `% Completion` is normalized to 0%** for every new Excel work item. The importer accepts whole percentages 0–100, including `35`, `35%` and Excel's numeric `0.35` formatted as `35%`.
- Safe preview and atomic confirmation: matched existing work rows default to **Keep existing**, so uploading a blank completion cell never silently erases previously recorded progress. Explicit `Update details + percentage` can reset an existing row to 0% and records history.
- Actual work percentages drive category and overall project completion; no binary complete-only calculation. Empty categories and archived/cancelled works do not reduce the project average.
- The upgraded Work Progress, Work Categories, Works, Import Works, and Update Progress interfaces from Upgrade 4 remain in place, along with the original permission checks and legacy URL aliases.

## Release-hardening fixes in Upgrade 5

1. **Category collision detection:** different Excel category headings that normalize to the same internal slug no longer silently merge (`Civil & Steel` and `Civil Steel`, for example). The import is stopped with a row-level explanation.
2. **Existing category identity:** an uploaded category name that conflicts with an existing category under the same normalized code is rejected for explicit correction. The category name is rechecked at confirmation, preventing stale preview merges.
3. **Ambiguous work serial numbers:** if the existing project contains multiple serial numbers equal under case-insensitive comparison (`ABC` and `abc`), the preview refuses to select one arbitrarily. Confirmation also guards against ambiguity created after preview.
4. Added Django regression tests for the above issues and the blank-percentage rule in `apps/project_pulse/tests/test_work_import_release_u5.py`.
5. Added a reproducible standalone (no Django required) verification script at `scripts/verify_project_pulse_u5_offline.py`.

## Actual verification performed in this packaging environment

- **19 / 19 offline checks passed** using the production Excel parsing and rollup functions extracted directly from source, with a small substitute for Django's `slugify` in ASCII test cases. This includes parsing the prepared BOQ: **151 works, 9 categories, 0 parser errors**.
- Progress calculation check: category percentages 45% and 30% produce **37.5% project progress**; cancelled works and an empty category are excluded.
- Python source compilation and Project Pulse migration/URL presence checks passed.
- Project Pulse JavaScript syntax passed `node --check`.
- ZIP member paths and integrity are checked during packaging.

**Not executed:** Django's system checks, ORM integration tests, PostgreSQL migrations, permission/transaction behavior against a database, and browser visual/interaction tests. The build environment has no Django installation and cannot retrieve the required package. The new Django test cases are included but have **not** passed here. **Do not treat this archive as a verified production release until staging checks pass.**

## Required staging release checklist

1. Take a **verified database backup** and a copy of the currently running application. Test using a separate staging database, not directly on live production data.
2. Deploy the complete source package (or apply only the U5 patch over an exact U4 installation). Install the project's pinned requirements from `requirements/base.txt` using the configured environment.
3. In staging, run:
   ```bash
   python manage.py check
   python manage.py migrate --plan
   python manage.py migrate --noinput
   python manage.py test apps.project_pulse
   python manage.py check --deploy
   ```
   Review any environment-specific `check --deploy` warnings; do not disable protections merely to silence them.
4. With a user having both Work Category and Works management permissions, import the prepared BOQ. Verify 9 categories / 151 works and that all initially blank completion cells become 0%.
5. Update one work manually to 35% and then 100%. Verify its status, work history, category totals, and project total. Exercise On Hold and Blocked without erasing a partial percentage.
6. Reimport the same workbook. Confirm no duplicate works, and that a blank completion cell for a previously progressed task **does not overwrite** its saved percentage unless explicitly selected in the preview.
7. Use role-limited accounts to confirm unauthorized category import, progress editing, and cross-project access are rejected. Test an expired/stale preview and malformed or ambiguous work categories/SNs.
8. Verify navigation labels, import preview, large tables, work search, forms, responsive behavior, and static assets in the browser. Smoke-test existing Inventory, Payroll, Expenses, Budget, approvals, and reports before promoting to production.

### Docker note

This repository defines the service as `ims_web` in `docker-compose.yml`. After staging deployment, the system checks and tests can be run through its configured application service (for example, `docker compose exec ims_web python manage.py check`). Database migrations can affect state; do not run them before backing up and verifying a staged rollout.

### Migrations

Upgrade 5 adds **no database migration**. Upgrades 1–3 added `project_pulse.0008_work_import_foundation` and `project_pulse.0009_work_import_preview`; they are still required if not previously applied.
