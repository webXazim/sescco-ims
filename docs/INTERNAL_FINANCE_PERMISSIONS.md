# Internal Payroll + Finance permissions — 1.0.97

Carried forward unchanged in SESCCO MS 1.0.98.

SESCCO MS separates payroll preparation, finance review, final approval and payment execution. The backend is authoritative; hiding a button in the browser is never treated as a security boundary.

## Built-in duty separation

**Internal Payroll Officer** maintains Internal employees/organization data, attendance input, salary setup, payroll calculation and submission, adjustments preparation, payment preparation and Bank/WPS export. The profile cannot perform Finance Review, final payroll approval or payment execution.

**Finance Reviewer** can review a submitted payroll snapshot, return it for correction, approve attendance and approve adjustments. The profile cannot calculate/prepare payroll, final-approve payroll or execute salary payments.

**Finance Manager** can final-approve a payroll run after a valid independent Finance Review and can execute/reconcile payments. The profile does not inherit Finance Review authority, employee-master maintenance, salary-setup maintenance or payroll calculation/preparation authority.

The Company Owner retains full emergency permissions, but workflow service rules still enforce separation of actors: the payroll submitter cannot sign the Finance Review; the final approver cannot be the payroll submitter or the Finance Reviewer.

## Payroll workflow

1. Payroll Officer completes/locks the source attendance and calculates payroll.
2. Payroll Officer submits the immutable payroll snapshot to Finance Review.
3. A different user with `internal.payroll_runs.review` records **Mark Reviewed** or returns the run for changes.
4. A different user with `internal.payroll_runs.approve` performs **Final Approve**. Approval fails closed when review evidence is absent or when the final approver is the submitter/reviewer.
5. Bank/WPS files require `internal.wps.export`; this permission does not authorize payment posting.
6. Payment execution/reconciliation requires `internal.payments.execute`.

Review evidence is persisted on `PayrollRun.reviewed_at` and `PayrollRun.reviewed_by`; final approval continues to use the existing approved timestamp/user evidence. Any recalculation/resubmission clears stale review evidence.

## Custom Access Profiles

Custom profiles may use the same granular permissions, but service-level actor separation still applies even if one profile is accidentally granted prepare + review + approve. This prevents a broad custom profile from bypassing the workflow separation.

For production deployment of 1.0.97, run the packaged PostgreSQL/Docker rehearsal because migrations `accounts.0010_internal_finance_permission_decomposition` and `internal_payroll.0014_payroll_review_signoff` change the database schema and built-in Finance grants.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.111.
