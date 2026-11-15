# SESCCO IMS v1.0.129 — Project inventory sorting correction

## Cause

The prior inventory upgrade added the sort control to Inventory Explorer and Office Stock, but the separate project inventory page at `/app/projects/<PROJECT-CODE>/` still forced material-name ordering. It also had no `sort` selector in its project stock filters.

## Fixed behavior

- Project inventory defaults to **Recently added first** (stock-record `created_at` descending, stable `pk` tie-breaker).
- The `Sort project inventory` dropdown now offers oldest added, recently/oldest updated, material name A–Z/Z–A, highest/lowest quantity, and newest/oldest stock receipt.
- Sort applies before pagination and remains selected during search, stock-status, record-status and page changes.
- Reset restores `Recently added first` and the default filters.
- CSV and Excel exports use the same sort policy as the project listing (not a separate alphabetical default).
- Invalid query-string sort values fall back to `Recently added first`; arbitrary ORM ordering is not accepted.
- No database migration, stock-quantity change, movement rewriting, permission change, or version bump is required.

## Modified files

- `apps/projects/views.py`
- `apps/projects/stock_sort.py` (new shared allowlist)
- `templates/projects/project_detail.html`
- `apps/data_exchange/services/exporting.py`
- `apps/projects/tests/test_projects.py`

## Verification

Passed offline source freeze: `bash scripts/verify-production-freeze.sh`. Python syntax parsed. The Django/PostgreSQL tests need to be run on your Ubuntu staging server:

```bash
python manage.py check
python manage.py test apps.projects.tests.test_projects apps.data_exchange.tests.test_exports --noinput
```

Apply the hotfix to an existing 1.0.129 deployment, review and commit the intended Git changes, and use the existing production deployment script. The existing v1.0.129 static manifest deployment fix remains included in the complete application.
