# SESCCO MS lifecycle and retention policy

SESCCO MS intentionally does **not** give every record the same Delete or Archive button.
The safe action depends on what the record represents.

## Master records

Branches/offices, departments, internal employees, manpower suppliers, rental workers, projects,
inventory units/suppliers/locations/stock records, salary components, overtime policies and Bank/WPS
export templates use the central lifecycle authority. Real records are archived so historical links stay
valid. Permanent **Delete unused** is reserved for mistaken/duplicate setup and is rejected when protected
history exists.

Employee payment profiles are slightly different: an unused profile may be deleted, but once salary-payment
history exists it must be made inactive instead.

## Records that are not master-data delete candidates

- Internal salary structures and employee organization assignments are effective-dated. Change them by
  creating the next effective record; do not rewrite or archive history.
- Payroll runs, attendance periods, adjustments, salary-payment batches, rental assignments, timesheets,
  settlements, supplier payments, stock documents and transfers follow their own workflow states.
- Stock movements, audit events, payment attempts/results, finalized payroll snapshots and finalized
  business documents are historical evidence. They are immutable/reversal-based, not ordinary delete/archive records.
- System users and company memberships are deactivated/reactivated rather than deleted so audit actor
  history remains resolvable.
- Company identity/settings, salary-payment settings, payroll policy and numbering sequences are singleton
  or system state and are updated in place under permission/audit controls.
- Saved views/table preferences are user-owned convenience data and may be deleted normally.

The machine-readable authority for this classification is `merge/lifecycle-retention-contract.json`.
`verify-lifecycle-retention-contract.py` fails the production freeze if a persisted SESCCO model is added
without an explicit retention classification or if key UI/API safeguards regress.
