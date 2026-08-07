# Upgrade 4 — Complete storekeeper workspace

This upgrade connects the remaining approved operational interactions to persisted Django data and strengthens the lifecycle rules around projects, stock records and historical identity.

## Completed

### Storekeeper workflow completion

- Dashboard project scope now drives stock counts, attention counts, recent activity and action links.
- Project pages show operational summary counts, current inventory, active/archived record filtering and recent project movements.
- Add-stock actions remain prefilled from project and stock-detail pages.
- Use-stock now starts with a project and provides a server-backed material/supplier/phone search picker.
- The stock picker loads only active, positive-balance records from the selected active project.
- Stock details expose edit, add, use, adjust and lifecycle actions only when valid.
- Low-stock, inventory and activity pages remain server-paginated and permission protected.
- Inventory defaults to active records while archived records remain explicitly searchable.
- Latest price and latest addition date are visible in the current-stock table.

### Safe project and stock-record lifecycle

- Projects can be completed or archived only when every linked stock balance is zero.
- The rule is enforced by both forms and model validation, including Django admin writes.
- Stock records can be archived only at zero balance.
- Archived stock records retain all history and can be reactivated only under an active project and active unit.
- Stock-record status is changed through a dedicated transaction-safe service instead of direct form editing.
- Units with active stock records cannot be deactivated accidentally.

### Historical identity integrity

- Every movement stores snapshots of project code/name, material name, supplier name/phone, normalized phone search data and unit symbol.
- Existing movements are backfilled through migration `0004_movement_identity_snapshots`.
- Editing current material or supplier metadata no longer changes what historical movement pages display.
- Reversal movements reuse the original movement identity snapshots.
- Reversals require an active project and active stock record, preserving closed-project lifecycle invariants.
- Project and unit are locked after the first movement to prevent historical stock from being reassigned.
- Movement search includes snapshot fields as well as current stock metadata.

### Interface and interaction quality

- Project-aware usage picker uses debounced server search and cancels stale browser requests.
- The picker has a no-JavaScript server-validation fallback.
- Live balance previews continue to warn before negative usage while the server remains authoritative.
- Lifecycle actions use POST, CSRF and explicit confirmation.
- Archived/inactive states have clear interface notices and invalid action buttons are not shown.
- Movement and dashboard labels use immutable historical snapshots.

### Tests added

Coverage is included for:

- movement identity snapshots surviving metadata edits;
- project and unit locking after stock history exists;
- zero-balance archive/reactivation rules;
- positive-balance archive rejection;
- project-aware stock picker search;
- project completion rejection while stock remains;
- project-detail active/archived record filtering;
- historical phone search after current supplier metadata changes;
- reversal blocking while a project or stock record is inactive;
- active-unit deactivation protection.

## Deliberately deferred

Upgrade 5 implements advanced all-column filtering, date presets, custom date ranges, URL-persisted filter state and saved views. Upgrade 6 implements exact-result XLSX/CSV export and the reviewed Excel migration workflow.
