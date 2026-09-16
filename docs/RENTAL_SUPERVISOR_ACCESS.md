# Rental Supervisor / Foreman access

SESCCO MS 1.0.92 introduces a built-in **Rental Supervisor / Foreman** Access Profile for project-site attendance supervision. The profile is intentionally operational rather than financial.

## Granted authority

The built-in profile has exactly nine permissions: Rental overview, workers and assignments view; Rental timesheet view/edit/submit; and Rental overtime view/edit/submit. It does not approve timesheets or overtime and does not manage workers, assignments, suppliers, adjustments, settlements, payments, documents, reports, Archive or Delete recovery.

The normal production setup is **Administration → Users → Access Profile: Rental Supervisor / Foreman → Project scope: Selected**, then choose the projects the supervisor is responsible for. `All` and `None` remain available for explicit administrative use.

## Security boundary

Project scope is enforced in backend selectors and mutation services. It is not a sidebar-only filter. Worker/project directories, assignment history, timesheet reads, attendance writes, overtime writes and timesheet workflow requests revalidate the selected project against the membership scope. An out-of-scope direct API request is rejected.

Supplier financial data is outside this profile. Supplier/settlement/payment routes require their exact permissions, and settlement metrics are not constructed for the Foreman bootstrap. Assignment commercial rates are serialized as `Restricted`/`null` unless the caller has settlement visibility or assignment-management authority.

The Foreman may submit a Draft project timesheet for review. Approve, lock and return-to-draft require `rental.timesheets.approve`, which the built-in Foreman profile does not have. This preserves separation of preparation and approval.

## Production verification

Static release verification:

```bash
python3 scripts/verify-rental-supervisor-scope.py
python3 scripts/verify-payroll-production-e2e.py
bash scripts/verify-production-freeze.sh
```

Runtime certification in the Docker/PostgreSQL release environment executes `apps.rental_manpower.tests`, including the scoped-supervisor regression suite, through `scripts/certify-payroll-production-e2e.sh`.
