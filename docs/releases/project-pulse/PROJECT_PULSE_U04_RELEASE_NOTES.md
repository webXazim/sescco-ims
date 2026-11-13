# SESCCO Project Pulse — U04: Weighted Physical Progress and Update History

**Full application version:** `1.0.121`  
**Base:** `SESCCO_IMS_Project_Pulse_U03_v1.0.120_Full.zip`  
**Scope:** Operational progress only. **No connection to Payroll or Inventory; no expenses, budgets, contract figures, or profit/loss introduced.**

## Changes

- Task completion percentage (`0`–`100`) and positive, configurable **task progress weight** (default `1.00`).
- Positive, configurable **work-category progress weight** (default `1.00`). These are relative operational weights, not budgets or currency.
- New audit-backed per-task progress-history records containing old/new percentage, old/new status, updater, timestamp, and optional note (up to 2,000 characters).
- An assigned team member with explicit Progress/Update permission may update their own task. A current Project Pulse project manager with that permission, or an authorized Tasks/Manage user with Progress/Update permission, can update other tasks in their accessible projects. Project/company scopes and active-project restrictions continue to apply.
- Status rules: `Completed` must be `100%`; `Not started` must be `0%`; other statuses must be below `100%`. The existing task editor retains its previous status workflow and automatically synchronizes percentage and writes history when status changes.
- Project overview, project directory, work category list, task lists, My Tasks, and a new task progress/history page display operational progress when authorized.
- Weighted category progress = sum(task % × task weight) ÷ sum(task weight).
- Weighted project progress = sum(category progress × category weight) ÷ sum(category weight), computed without intermediate rounding.
- Archived tasks/categories and cancelled tasks are excluded from the denominator and numerator. Categories without eligible tasks do not dilute project progress. Empty projects show “No tracked tasks”, not a completed metric.
- Progress updates preserve audit history. Authorized managers can still update a task whose former assignee has lost project access; the former assignee cannot do so.
- New `pulse.progress.view` and `pulse.progress.update` Access Profile permissions. Owner profiles receive them via migration, while other profiles must be granted explicitly.
- Regression tests added for calculation accuracy, historical updates, assignment/permission boundaries, company/project scoping, archived/closed work, task-editor compatibility, and no finance module coupling.

## Database migrations

1. `accounts.0020_project_pulse_u04_progress_authority` adds the two valid access-permission values and seeds them to Owner profiles only.
2. `project_pulse.0003_weighted_progress` adds weights, percentages, consistency constraints and progress-history table. It backfills **existing Completed tasks to 100%** before applying database constraints; no fictitious historical update is created during this backfill.

**Before deployment:** back up the database and application; test migrations in staging. This upgrade is source-level validated, but a live Django installation/database was not available to execute the migrations or test suite in this environment.

## Deployment / verification

From the application's configured Python environment:

```bash
python manage.py migrate
python manage.py check
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

Restart application services after successful checks. Verify the new Progress/View and Progress/Update permissions in **Administration → Access Profiles**.

## Files added or changed

- `apps/project_pulse/progress_services.py` (new)
- `apps/project_pulse/migrations/0003_weighted_progress.py` (new)
- `apps/project_pulse/tests/test_progress.py` (new)
- `templates/project_pulse/task_progress.html` (new)
- Project Pulse models, forms, services, access rules, routes and pages
- `apps/accounts/access_catalog.py`, `apps/accounts/access_profiles.py`
- `apps/accounts/migrations/0020_project_pulse_u04_progress_authority.py` (new)
- Project Pulse stylesheet and version metadata

## Pending modules

- **U05:** Separate task-specific expense categories and expense records.
- **U06:** Expense approvals, attachments, payment status.
- **U07:** Category budgets and automatic budget calculations.
- **U08:** Confidential contract values and profit/loss forecasting.
- **U09:** Reporting and export.
- **U10:** Comprehensive end-to-end hardening and release verification.
