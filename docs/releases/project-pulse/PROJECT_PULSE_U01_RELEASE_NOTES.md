# SESCCO Project Pulse — U01 foundation

Version: 1.0.118; base: sescco-ims-all-fixes-user-transfer.zip (1.0.117).

## Implemented
- Fifth independently permissioned module: **Project Pulse** (`/app/project-pulse/`).
- Dedicated shell/sidebar and module switcher entry. Shell never links to inaccessible modules.
- Project overview with company/project-scope-safe counts (active/on-hold/completed), and visible project list.
- Searchable, status-filtered, paginated project directory and read-only detail pages.
- Existing `apps.projects.Project` is reused; no duplicate project model, project rows, or financial records.
- Two explicit permissions in Access Profiles: `pulse.overview.view` and `pulse.projects.view` (directory requires overview).
- Database check-constraint migration and company-owner system-profile grant backfill.
- Separate Django test coverage of permissions, multi-company isolation, project scope, routing and no-write behavior.
- No implicit access for built-in Project Manager, Inventory Manager, Finance or other roles.

## Deliberately not yet implemented
- U02: Pulse-specific project manager/team assignments and granular working permissions.
- U03–U04: work categories, tasks, progress and history.
- U05–U06: independent task expense ledger and approvals.
- U07–U08: category budgets, private contract values, profit/loss.
- U09–U10: reports and comprehensive acceptance tests.

## Deployment
1. Back up the production database and application files.
2. Replace application source using the full new archive; preserve your .env and production data.
3. Run: `python manage.py migrate` in the configured application environment.
4. Run: `python manage.py collectstatic --noinput` if using production staticfiles.
5. Restart the application services.
6. Sign in as owner; use the module switcher to open Project Pulse.
7. For non-owners, create/clone a custom Access Profile granting **Project Pulse · Overview / View** and optionally **Project Pulse · Projects / View**, then assign intended users with correct project scopes.
8. Run: `python manage.py test apps.project_pulse` with a correctly configured test database. Check all existing modules before production cutover.

This release is intentionally **read-only** for Project Pulse. The latest Inventory, Payroll, Sourcing and Access Profile functionality remains packaged unchanged except for the module integrations described here.

## Validation note
The build environment does not have Django installed, and package installation could not reach the package registry. Python static compilation/ZIP verification were performed; Django management checks, migration application, and runtime tests require a working installation.
