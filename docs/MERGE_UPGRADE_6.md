# Merge Upgrade 6 — Internal Payroll Backend

This upgrade imports the production Internal Payroll domain from the frozen PRS source into the merged IMS Django project.

## Authority retained from IMS

- `accounts.User` remains the only authentication model and keeps its existing integer primary keys.
- `core.Company` / `accounts.CompanyMembership` remain the tenant and authorization authorities.
- The existing IMS PostgreSQL database, Compose project, and named volumes are unchanged.
- All frozen IMS/merge migrations remain immutable.

## Internal Payroll imported

The `apps.internal_payroll` domain includes branches, departments, employees and effective-dated organization history; salary components, overtime policies and salary structures; monthly attendance and overtime; payroll policies, runs, snapshots and adjustments; and salary-payment/WPS configuration, encrypted payment profiles, export templates, batches, attempts and result imports.

The API contract remains `/api/internal/...`; the frozen DocGen V2 Payroll frontend is now attached through Upgrade 9 and participates in the shared Business/Area shell introduced by Upgrade 10.

## Merge adaptations

- The PRS core migration dependency was replaced by the merged platform `core.0001_platform_core` dependency. No business schema from Internal Payroll was otherwise rewritten.
- PRS `accounts`, `core` models, and UUID user identity were not copied.
- Generic decimal field helpers and Fernet-backed encrypted text support were added to the existing platform core because salary payment/WPS data requires them.
- `PAYROLL_FIELD_ENCRYPTION_KEY` is mandatory in production and must remain stable for the lifetime of encrypted payroll banking data unless a deliberate key-rotation migration is performed.
- Internal Payroll Django admin is active-company scoped and read-only. Operational changes continue through audited services.
- Internal-workspace membership is required for all Internal Payroll APIs; edit, approval and payment services continue to enforce their finer capabilities.

## Staging / production validation

After migrations run:

```bash
python manage.py merge_internal_payroll_report --fail-on-errors
python manage.py check --deploy --fail-level ERROR
python manage.py makemigrations --check --dry-run
```

The reconciliation command verifies every Internal Payroll model has a company and every FK between company-owned payroll records stays inside the same company.

## Secret generation

Generate the production encryption key once, store it securely outside the repository, and back it up separately:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

Never replace this key casually after encrypted payment-profile records exist.
