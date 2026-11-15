# Project Pulse — Execution-first UI refinement (v1.0.130 hotfix)

## Scope

Refines the Project Pulse interface without changing the underlying models, business calculations, approval workflows, user permissions, migrations, or application version.

### Project overview

- Leads with the project name, status, and direct execution-schedule action.
- Combines physical completion and scheduled-work counts into one high-priority progress band.
- Makes the execution-category table the primary workspace, with compact completion indicators and direct links to the work list for authorized users.
- Shows one permission-controlled financial snapshot for approved expenses, category budgets, and forecast final profit. Each figure is visible only with its existing access permissions; the previous full-width repeat panels have been removed.
- Collapses project-register metadata under a native, keyboard-accessible details control.
- Groups reports, team membership, and expense classifications under compact links rather than standalone full-width cards.
- Gives empty projects/categories useful setup guidance while continuing to show 0% progress.

### Navigation

- Keeps top-level navigation to Overview and Projects.
- In the selected-project context, offers Project overview, Execution schedule, and Reports.
- Groups financial pages in a collapsed Financial controls disclosure, shown only with appropriate permissions.
- Groups secondary actions (all scheduled works, expense categories, team) under More tools.
- Expands the group containing the currently active financial or settings page.
- Reuses the existing SESCCO sidebar, project/company permission checks, and existing routes.

### Schedule directory and module overview

- Simplifies the execution-category table to emphasize work counts and progress.
- Replaces the extra row of oversized multi-project progress metrics with a compact summary strip.
- Adjusts spacing, typography, table density, and responsive layout throughout Project Pulse.

### Operational and security guarantees

- No change to project progress formulas (finished scheduled works, 0% for an empty category).
- No change to approved expense, budget, or profit calculations.
- No change to the independent Inventory or Payroll modules.
- No new migrations, access permission values, or application version changes.
- Approved expenses and private financial figures still require the same explicit permissions; navigation is not a security boundary.

## Checks and deployment

Offline checks: `python scripts/project_pulse_u10_offline_checks.py` and `bash scripts/verify-production-freeze.sh`.

Staging tests (configured Django/PostgreSQL):

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

Confirm visually on desktop and mobile: project overview, execution schedule, expense links, budgets, profitability, reports, and access profiles with no financial permissions. For Docker deployments run these checks using the configured application service. Collect static files and restart application workers during deployment. Retain a backup of the database and private expense documents even though no schema changes are introduced.
