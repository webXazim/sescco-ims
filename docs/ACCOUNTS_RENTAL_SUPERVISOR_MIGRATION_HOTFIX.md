# Accounts Rental Supervisor Migration Hotfix — 1.0.117

`accounts.0008_rental_supervisor_profile` is a historical data migration that creates the system Rental Supervisor / Foreman Access Profile for each company.

The broken migration resolved `Company` from the `accounts` app even though the authoritative historical model is `core.Company`. On a database that had not yet applied `accounts.0008`, Django therefore failed with `LookupError: App 'accounts' doesn't have a 'Company' model.`

1.0.117 corrects that historical lookup to `apps.get_model("core", "Company")` and routes all migration-time ORM operations through `schema_editor.connection.alias`. The migration remains named `accounts.0008_rental_supervisor_profile`; do not fake it.

PostgreSQL migrations are transactional by default, so the failed attempt should have rolled back. Deploy 1.0.117 and rerun the normal migration pipeline.

Required runtime confirmation:

```bash
python manage.py check --deploy --fail-level ERROR
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
```

The only acceptable deployment-check warning carried from prior releases is the configured HSTS preload warning unless operations intentionally enables preload.
