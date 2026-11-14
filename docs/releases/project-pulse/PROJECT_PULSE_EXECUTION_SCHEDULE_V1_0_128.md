# Project Pulse — Execution Schedule Upgrade (SESCCO IMS v1.0.128)

## Scope and design

Project Pulse is now presented as **project execution schedule management**. Project -> Execution category -> Scheduled works -> expense category and individual expense entries. Shared project identity, expense approvals, payment tracking, budgets, profitability, reports, audit history, and Inventory/Payroll isolation are preserved.

- **Navigation:** Overview and Projects are always available to their permitted profiles; after selecting a project, scoped links for Execution schedule, Scheduled works, Work expenses, Expense categories, Category budgets, Profitability, Reports and Project team appear according to explicit access profiles. Removed the My Tasks link and dead-end placeholder links. The old `my-tasks/` URL remains for compatibility with existing bookmarks.
- **Category forms:** Work category renamed to Execution category; no progress percentage or progress-weight input. Existing model defaults to weight 1; old weights and historical records remain stored, but weights are no longer used for reporting operational completion.
- **Scheduled works:** These reuse the existing protected PulseTask model so prior expenses and audit history remain attached. No assignee is needed in the normal form. Existing assignment and priority values are preserved when editing old rows. Scheduled work can be marked Complete or Reopened with one click, using the existing transaction-protected, permission-checked progress service, CSRF, audit history and project-scope validation. Status details remain editable separately.
- **Category progress:** 100 * completed work count / active, non-archived, non-cancelled work count; no works => 0%. Partial legacy percentages do not contribute until status = Completed.
- **Project progress:** Equal average of progress across all active execution categories, **including empty categories as 0%**. No active categories => 0%. This makes the effect of future/unstarted scheduled stages clear. The percentage is physical progress, not budget utilization.
- **Finance:** Task expense ledger stays independent of Inventory/Payroll. Each scheduled work links to its expense list; categories reused within the project. Amounts/budgets/profit appear only if the corresponding financial permissions are granted. No database schema/migrations added.
- **Legacy URLs:** Existing `/categories/`, `/tasks/` and old task expense URLs continue functioning. New readable aliases `/execution-schedule/` and `/scheduled-works/` were added. New per-category schedule URL and audited completion POST route added.
- **Reporting:** Progress reports now use status-based completion and show Scheduled work / Execution category labels; budget and expense reports remain financial-permission controlled.

## Staging verification (required)

Back up the database and private receipt-storage volume. Inspect the diff and commit through the normal release process; the deployment preflight expects a clean Git tree. The production deploy script synchronizes only the private `APP_VERSION` with `VERSION=1.0.128` using a protected backup.

```bash
cd /opt/sites/ims
sudo bash scripts/verify-production-freeze.sh
# Execute in the configured app environment / container:
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse --noinput
# After staging acceptance, use the existing production deployment procedure:
sudo bash scripts/deploy-production.sh
```

Manual acceptance: create an empty category, verify 0%; add 4 scheduled works, complete 2 -> 50%; reopen -> 25%; verify another empty category counts 0% in the project average; verify a work's expense categories/entries, approved costs and private receipts still exist; test non-financial profile cannot see SAR/budget/profit; test scoped user denied another project; verify backups before rollout.

## Verification status

Passed here: 708 Python AST files, 50 Project Pulse routes/template links, 124 permissions, offline XLSX/PDF generation, production source verifier, immutable migration baseline, Inventory/Payroll/security checks and ZIP integrity. Django/PostgreSQL integration suite and browser acceptance are **not available in this environment and have not been executed**.
