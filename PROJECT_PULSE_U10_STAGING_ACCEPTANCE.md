# Project Pulse U10 — staging acceptance checklist

**Release:** SESCCO IMS `1.0.127`, built from the complete U09 `1.0.126` archive.  
**Deployment gate:** **NOT APPROVED** until all items below pass in a configured staging environment. This release introduces no new database schema and requires no new migration; apply all earlier migrations from U01–U09 if not already applied.

## 1. Prepare, back up, and verify

- [ ] Record previous production release, database migration state and installed roles.
- [ ] Take and verify a restorable PostgreSQL backup and all media and **private Project Pulse evidence** (`ims_pulse_private_data`). Keep backups outside the replacement application directory.
- [ ] Deploy in staging with the configured `.env.production` and `APP_VERSION=1.0.127`; do not overwrite existing secrets.
- [ ] Install pinned `requirements/base.txt` (including Django, PostgreSQL adapter, openpyxl, ReportLab).
- [ ] Run `bash scripts/verify-project-pulse-u10.sh` from the app root. This includes source/export smoke, Django system checks, migration drift/dry run, pending migration plan, and all Project Pulse Django regression tests.
- [ ] Run `python manage.py check --deploy --settings=config.settings.production` under a production-like staging environment; review warnings and proxy/TLS configuration.
- [ ] Apply the planned migrations in staging: `python manage.py migrate`, then `python manage.py collectstatic --noinput`; restart services and check health endpoints.
- [ ] Confirm database and private-file restoration from a separate copy before any production upgrade.

## 2. Access profiles and isolation

- [ ] Owner has full Project Pulse control, including finances; no Inventory-only or Payroll-only profile inherits Pulse permissions.
- [ ] Overview-only custom profile can view aggregate project counts **without** project names, client names or task details.
- [ ] Projects/View profile sees only its assigned project scope. Direct URL to a different project or company is denied.
- [ ] Task/progress-only profile sees no amounts, expense documents, approved budgets, contract value, profitability, or financial export data.
- [ ] Expense-only profiles see only the specific financial areas granted. Budget/Profit/View and report export require independent permissions.
- [ ] Private attachment direct URLs require authenticated expense-view authority. The private file volume is not served by Nginx `/media` or `/static`.
- [ ] On revoking a user/profile/project scope, check that their existing session can no longer read reports or download documents.
- [ ] Attempt direct report export URLs for every report type with a user denied the underlying permission; confirm 403 and no file bytes.

## 3. Operations and audit

- [ ] Create a project team, work categories, tasks, assignments and weighted progress updates; validate task status and completion history.
- [ ] Confirm pending/rejected/voided expenses do not enter approved totals, and approved entries survive task/category archive.
- [ ] Attempt a non-owner self-approval for expense, budget, and contract: verify it is denied. Verify reviewed approvals are immutable.
- [ ] Upload PDF/JPG/PNG/WebP receipts, reject invalid file signatures, then download with valid permission.
- [ ] Record partial and full payments; reject overpayment and verify void/reversal does not erase history or expense cost.
- [ ] Propose/review category budgets; test a true approved zero versus a missing budget.
- [ ] Verify expense in an **unbudgeted** task category remains in total cost, but is not deducted from another category's approved-budget balance. Verify the distinct unbudgeted-cost warning.
- [ ] Archive a task/category containing approved expenses but **no budget**: ensure costs remain, and planned-profit figure is withheld until budgeting is complete.
- [ ] Approve base contract, positive/negative variations and remaining-cost forecast; compare forecast profit and margin to independently calculated SAR figures. Confirm refreshed/stale-forecast warnings.
- [ ] Verify general audit log does not expose expense amounts, payment details, contract figures, or private notes; restricted histories remain accessible to authorized finance users.

## 4. Reporting, browser, and release readiness

- [ ] Compare screen and XLSX/PDF totals for progress, expenses, budgets and financials (including filters, 0-row reports and multi-page reports).
- [ ] Verify formula-style supplier/description text in XLSX is inert; test long names and both decimal and negative values.
- [ ] Verify Arabic and other non-Latin text **separately**: current ReportLab Helvetica PDF fonts are not certified for Arabic shaping; do not claim multilingual PDF support without review.
- [ ] Confirm Inventory, Rental Manpower, Internal Payroll, Sourcing and Administration workflows still function: login, list, create, updates, approvals, exports, custom profile saves.
- [ ] Run host monitoring, gateway and database health checks after staging deployment.
- [ ] Obtain acceptance by the responsible release owner based on test logs/screenshots; only then plan production deployment and rollback.

## Current evidence / limitations

The release package contains automated regression tests, a dependency-light offline validator, and this checklist. The preparation environment lacked `Django` and `psycopg`, so **real ORM queries, PostgreSQL migrations, authenticated HTTP responses, browser security and end-to-end tests were not run here**. Passing syntax, static policy, and export smoke checks is **not** equivalent to production readiness.
