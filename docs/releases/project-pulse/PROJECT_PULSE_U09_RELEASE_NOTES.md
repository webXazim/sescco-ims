# SESCCO IMS — Project Pulse U09

**Application version:** 1.0.126 (built on U08 v1.0.125 source archive)

## Added

- A per-project **Reports & Analysis** page with four independent report types:
  1. **Task progress** — task status, assignee, priority, weight, due date, and unfiltered overall weighted project completion.
  2. **Task expenses** — recorded, pending, approved, paid, and outstanding expense amounts; includes archived-task costs and excludes voided entries/payments.
  3. **Category budgets** — current approved category budgets versus approved expenses, remaining balances, and over-budget/missing-budget indicators.
  4. **Project profitability forecast** — approved base contract, variations, approved costs, estimated final cost and forecast final profit/margin. Missing values remain unavailable, never invented.
- Filters: progress by task due-date range, status and work category; expenses by expense-date range, approval status, expense category and work category; budgets by work category. Budget and profit reports are **current snapshots** and explicitly reject date filters.
- Report totals are calculated from the **full filtered dataset**, not only the visible pagination page.
- Per-report **Excel (.xlsx)** and **PDF** exports use the same server-side filtered data and are subject to their own explicit permission.
- Export headers, paginated PDF tables, XLSX formatting, safe-text handling against spreadsheet formula injection, private/no-cache response headers and general audit entries without financial figures.
- Small cross-project operational summary on the main Project Pulse overview (only the listed projects, correctly labelled; no financial leakage).
- Two custom-profile permissions: `pulse.reports.view` and `pulse.reports.export`. Database constraint migration `accounts.0025_project_pulse_u09_report_authority` grants them to built-in Owner system profiles only. Other users are opt-in. Source data permissions are always required in addition.

## Security and accounting rules

- Every report and export rechecks the current company's project scope plus **the specific underlying data permission** (progress, expenses, budgets or profitability).
- Users with task/progress access cannot infer expenses or budgets; users with expenses access cannot infer contract values or profits. Export permission **does not** bypass report type permission.
- Client and supplier text is HTML-escaped in PDFs and formula-like text is forced to a literal string in XLSX. Exports have private cache headers.
- Approved expense cost **excludes** pending, draft, rejected, and voided records. Payment totals exclude voided payments. Payments do not double-count expense cost.
- The remaining-cost forecast is a point-in-time approved estimate; reports flag stale forecasts after approved changes. This is **not earned accounting profit**, revenue recognition, or VAT accounting.
- Maximum filtered rows per report: **5,000**. Exports do not silently truncate. Narrow filters if the limit is exceeded.
- Inventory and Payroll remain completely independent of Project Pulse expense data.

## Staging setup

1. Back up the database, project files and **private Project Pulse receipt volume**.
2. Deploy the complete U09 ZIP (do not deploy on top of a different code version without migration review).
3. Set `APP_VERSION=1.0.126` in the deployment environment.
4. Run from the configured Django environment:

   ```bash
   python manage.py migrate
   python manage.py check
   python manage.py makemigrations --check --dry-run
   python manage.py test apps.project_pulse
   python manage.py collectstatic --noinput
   ```
5. Restart services and perform end-to-end tests with Owner, operations-only, expense-only, selected-project and financial custom profiles. Check both browser pages and **direct export URLs**, including other companies' projects.
6. Verify multi-page XLSX/PDF reports and real project data in staging before any production release.

## Validation and known limits

- The entire Python source was AST-parsed, report URL/view references and template references checked, and the new 124-choice permission catalog checked against its database migration.
- Standalone Excel and PDF export generation was smoke-tested successfully using installed `openpyxl` and `reportlab`; a ten-column, 110-row PDF was rendered and visually inspected, including multi-page behavior.
- **Django database, HTTP, migration and full integration tests could not be executed here** because Django was not installed. Those tests are included (`apps/project_pulse/tests/test_reports.py`) and remain mandatory in staging.
- ReportLab's built-in Helvetica font is used, as in other application exports. Comprehensive multilingual/Arabic rendering is not yet validated; this should be verified during U10 hardening if project fields include Arabic.
- U08 source had an out-of-date `VERSION` file (`1.0.124`) despite its release name being v1.0.125. U09 corrects this to `1.0.126` and updates `.env.production.example`.

## Next

**U10 — Integration verification, security regression, migration and export hardening, production-readiness checklist and defects found during staging.**
