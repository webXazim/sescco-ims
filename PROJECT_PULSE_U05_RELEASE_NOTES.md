# Project Pulse U05 — Standalone Task Expense Ledger

**Release:** SESCCO IMS 1.0.122  
**Baseline:** SESCCO IMS 1.0.121 (U04 full source archive)  
**Change type:** Database schema + routes + new views + access profile permissions.  
**Status:** Built at code level; full Django runtime/database tests must be performed in an application environment.

## What changed

- U05 adds manual SAR expenses to existing Project Pulse tasks: Project → Work category → Task → Project-specific expense category → Expense entry.
- Each expense category is reusable across all tasks of **one project**, but not other projects. Category data and entry lists respect company/project scope.
- Expense entry includes date, description, positive SAR amount, optional supplier, reference, and notes. Edits and voiding are audited and saved in a finance-only revision history.
- The task page displays expense totals by expense category; the project page groups non-voided expenses by work category and expense category, including costs on archived work (to prevent totals from silently changing after archiving).
- The expense ledger is **independent** of both Payroll and Inventory. Neither source automatically creates or updates expense entries.
- Expenses are currently **recorded** or **voided**, with no approval/payment state. U06 adds approval, attachments, and payment status. Recorded totals are not equivalent to approved or paid costs.
- U05 does **not** add budgets, project revenue, or profit/loss reporting; those are scheduled for U07 and U08.

## Permissions

New custom access-profile permissions:

- `pulse.expense_categories.view` — view expense categories of authorized projects.
- `pulse.expense_categories.manage` — create/edit/archive categories for authorized active projects.
- `pulse.expenses.view` — view confidential expense entries, SAR amounts, totals, and revision history (requires task/project view).
- `pulse.expenses.manage` — add/edit/void expenses (requires expense view); only on active projects and active tasks.

Only the built-in system Owner profiles receive these permissions automatically via `accounts.0021_project_pulse_u05_expense_authority`. All other roles must explicitly be granted permissions, using Administration's access profile editor.

Sensitive expense values are **not** placed in the shared platform audit log; finance-only `PulseExpenseChange` records contain previous and new details.

## Migrations

- `apps/accounts/migrations/0021_project_pulse_u05_expense_authority.py`
- `apps/project_pulse/migrations/0004_expense_ledger.py`

The latter creates `PulseExpenseCategory`, `PulseExpenseEntry`, and `PulseExpenseChange`. Deletion of referenced categories/tasks is protected; public UI uses a void operation instead of deleting expense entries.

## Deployment

1. Back up both production database and existing application source. Stage the upgrade first.
2. Unpack the **complete** U05 ZIP over a staging copy, preserving environment configuration and stored user data.
3. In the configured Python virtual environment, run:

   ```bash
   python manage.py migrate
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test apps.project_pulse
   python manage.py collectstatic --noinput
   ```

4. Restart services only if migrations and tests succeed. Verify the Owner's expense category and task expense screens, and verify that unauthorized users cannot access any financial URL.
5. Open Project Pulse → Projects → selected project → Expense categories to create classifications, then Tasks → Expenses to enter records.

## Recommended staging acceptance cases

- Owner creates two tasks with expenses and sees exact SAR totals per task, expense category, work category, and project.
- Attempting to save an expense with zero/negative amount fails.
- A project A expense category cannot be used in project B (including when owned by the same company).
- A user with task/progress permissions but no expense view permission cannot see amounts in HTML or request expense endpoints.
- An authorized user with project B-only scope cannot reach project A expense pages.
- Voiding an expense requires a reason, removes it from active totals, preserves the record and history.
- Archiving a task leaves the project cost total unchanged, while preventing new entries.
- Expense change history is finance-only and shows prior/new values; shared audit logs do not contain sensitive expense values.
- Inventory, Payroll, Sourcing, Administration, and pre-U05 Project Pulse pages continue working.

## Verification completed in this build environment

- Python source parse/compilation and ZIP integrity checks.
- Source-level permissions/migrations/route/template consistency checks.
- Django runtime/database tests are included but **not executed** here because Django 5.2.17 is not installed in this runtime and the Python package index is unavailable. These tests remain necessary before production use.
