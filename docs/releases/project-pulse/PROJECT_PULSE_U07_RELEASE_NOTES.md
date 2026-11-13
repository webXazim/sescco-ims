# Project Pulse U07 — Category Budgets and Approved-Cost Calculations

**Release:** SESCCO IMS v1.0.124  
**Baseline:** U06 v1.0.123 full application  
**Status:** Implemented at source level; Django migration, HTTP and database tests must run in staging before production.

## Scope

- Standalone **work-category cost budgets in SAR**. An individual expense still belongs to a task and expense category. This feature does not integrate Payroll or Inventory.
- **Immutable budget revision history:** initial budget and each full replacement budget are submitted as a pending revision with a written basis. One pending revision per work category; an authorized reviewer approves or rejects it, retaining status, reviewer, timestamp and notes.
- **Approval authority separation:** `pulse.budgets.view`, `pulse.budgets.manage`, and `pulse.budgets.approve`; all depend on the finance view and existing Project Pulse task/project scope. Only the built-in system Owner is granted these permissions automatically by migration. Other custom roles must receive them explicitly. Non-owners cannot approve their own budget proposals.
- **Budget summary:** category approved budget, approved non-voided task costs, remaining budget, budget usage percentage, overrun notices, approved budget totals, project-level variance, and count of active categories without approved budgets. An approved zero budget remains distinct from an unset budget.
- **Historical accuracy:** archived task costs remain included, and archived work-category budgets remain in the project total. Changes are prohibited for archived categories and inactive/archived projects. Historical approved budgets are never overwritten when a new proposal is pending.
- **Access safety:** finance-only dashboards, secure server-side authorization for GET and POST routes, company/project isolation, and shared audit events without financial amounts or budget reasons.
- **UI:** project budget screen; propose budget form; approval/rejection controls; revision audit list; project overview link and totals for authorized viewers. Budget/profit figures do not appear to task-only users.

## Database migrations

1. `apps/accounts/migrations/0023_project_pulse_u07_budget_authority.py` expands the valid access-permission set and grants the three new permissions to built-in system Owner profiles only.
2. `apps/project_pulse/migrations/0006_category_budgets.py` creates `PulseBudgetRevision`, preserving all existing U01–U06 records.

No budget amount is automatically invented or approved during migration. An unbudgeted category appears as **Not set**, and the project summary warns that coverage is incomplete.

## Deployment

1. Back up the database and private receipt storage established in U06.
2. Deploy the **complete U07 ZIP** (not partial code) into a staging environment.
3. Set `APP_VERSION=1.0.124` in the deployment environment.
4. In the configured environment run:

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

5. Verify new budget view/write permissions in **Administration → Access Profiles** and assign them to selected finance users only.
6. Verify cross-company isolation, project scope, work-category budget history, zero/unset distinction and budget-overrun arithmetic.
7. Do not deploy to production until database and Django tests pass in staging.

## Limits and next steps

- Budget figures are **approved category cost budgets**, not contract revenue, planned profit, or cash flow.
- Expense *payments* and *expense approval* remain distinct: only approved, non-voided expenses count in budget actual costs, regardless of paid status.
- No task-level budget splits, contract values, profit/loss, or forecasted completion costs yet. **U08** will add contract and profitability reporting; U09 covers export/reporting, and U10 end-to-end hardening.
- Static checks are not a substitute for Django runtime/database and security testing; those cannot be claimed as complete without an installed Django environment.
