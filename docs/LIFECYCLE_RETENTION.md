# SESCCO MS lifecycle and retention policy

SESCCO MS intentionally does **not** give every record the same Delete or Archive behavior. The safe action depends on what the record represents.

## Archive and Delete

Archive and Delete are separate lifecycle operations.

- **Archive** is persistent and reversible. The master leaves current operations while historical references remain readable until the user restores it.
- **Delete** on selected operational masters is a recoverable 30-day soft delete, not immediate physical deletion.
- **Parent cascade is reversible.** Branch/Office, Department, Manpower Supplier and Project act as lifecycle boundaries. Their current operational child scope inherits Archive/Delete without rewriting child permanent status, assignments, payroll snapshots, stock history, settlement history, or audit evidence. Restoring the parent therefore restores only the scope hidden by that parent action.
- After the 30-day recovery window, SESCCO MS physically deletes a master only when Django's deletion collector proves that no related historical record would be deleted or protected. Otherwise the user-facing Delete item expires while a hidden historical tombstone remains so payroll, assignments, inventory, settlements, documents and audit evidence stay intact.

This lifecycle applies to branches/offices, departments, internal employees, manpower suppliers, rental workers and shared projects. Individual employees/workers can also be archived or deleted independently without first forcing an employment/status change.

Inventory units/suppliers/locations/stock records, salary components, overtime policies and Bank/WPS export templates remain on their existing central lifecycle rules. Their destructive delete operation is limited to unused setup records when protected history exists.

Employee payment profiles are slightly different: an unused profile may be deleted, but once salary-payment history exists it must be made inactive instead.

## Records that are not master-data delete candidates

- Internal salary structures and employee organization assignments are effective-dated. Change them by creating the next effective record; do not rewrite history.
- Payroll runs, attendance periods, adjustments, salary-payment batches, rental assignments, timesheets, settlements, supplier payments, stock documents and transfers follow their own workflow states.
- Stock movements, audit events, payment attempts/results, finalized payroll snapshots and finalized business documents are historical evidence. They are immutable/reversal-based, not ordinary delete/archive records.
- System users and company memberships are deactivated/reactivated rather than deleted so audit actor history remains resolvable.
- Company identity/settings, salary-payment settings, payroll policy and numbering sequences are singleton or system state and are updated in place under permission/audit controls.
- Saved views/table preferences are user-owned convenience data and may be deleted normally.

The machine-readable authority for this classification is `merge/lifecycle-retention-contract.json`. `verify-lifecycle-retention-contract.py` fails the production freeze if a persisted SESCCO model is added without an explicit retention classification or if key lifecycle safeguards regress.
