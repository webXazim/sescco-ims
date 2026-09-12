# SESCCO MS lifecycle and retention policy

SESCCO MS intentionally does **not** give every record the same Delete or Archive behavior.
The safe action depends on what the record represents.

## Archive versus Trash

Archive and Delete are separate lifecycle operations.

- **Archive** is persistent retention for a real master record that should leave current operations while its historical references remain available. It stays in the Archive Bin until deliberately restored.
- **Delete** on selected operational masters means **Move to Trash**, not immediate hard deletion. The record is hidden from active selectors immediately and remains recoverable from the Trash Bin for 30 days.
- When the 30-day recovery window expires, SESCCO MS physically deletes the master only when Django's deletion collector proves that no related record would be deleted or protected. If history still references the master, the Trash entry expires from the user-facing bin but the database retains a hidden historical tombstone so payroll, assignments, inventory, settlements, documents and audit evidence remain intact.

The 30-day Archive + Trash lifecycle applies to branches/offices, departments, internal employees,
manpower suppliers, rental workers and shared projects.

Inventory units/suppliers/locations/stock records, salary components, overtime policies and Bank/WPS export
templates remain on their existing central lifecycle rules. Their destructive delete operation is limited to
unused setup records and is rejected when protected history exists.

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
