# Project Pulse — Budget Overview Test Compatibility Fix (v1.0.130)

## Issue
On Ubuntu the Project Pulse test suite ran 90 tests with one remaining failed test:
`apps.project_pulse.tests.test_budgets.BudgetRevisionTests.test_budget_overview_visibility`.
The test expected the obsolete `Category budget control` heading. The redesigned
Project Pulse overview now consolidates that content under `Financial snapshot`.

## Correction
Updated the regression test to match the current UI and verify actual
permission boundaries and budget display, rather than an obsolete title:
- A user without `pulse.budgets.view` sees neither the financial summary nor the approved amount and cannot open the budgets page.
- A budget-view-only profile sees the approved budget and its link but not the confidential profitability forecast.
- An Owner sees the budget amount and can open the budget page.

No application business logic, templates, permissions, migrations, or deployment
configuration have changed. The release remains v1.0.130.

## Verification
- Python syntax of edited test: passed.
- `scripts/verify-production-freeze.sh`: passed.
- `python scripts/project_pulse_u10_offline_checks.py`: passed (routes, 124 permissions, PDFs/XLSX).
- Django/PostgreSQL runtime tests are **not run** in this build environment.

## Ubuntu acceptance
After installing the hotfix into the deployed source, run:
```
python manage.py test apps.project_pulse.tests.test_budgets --keepdb
python manage.py test apps.project_pulse
```
Use the project's container/test runner if the host Python environment lacks Django.
Only deploy after the tests pass. A Git-clean deployment must include this reviewed change.
