# Upgrade 3 — Safe inventory transaction engine

This upgrade makes quantity-changing operations production-structured while preserving the minimal project-specific inventory workflow.

## Completed

### Immutable movement ledger

- `StockMovement` records opening stock, additions, usage, positive/negative adjustments and reversals.
- Each movement stores previous balance, new balance, quantity, project stock record, date, reference, notes and responsible user.
- Addition movements may store unit price and a private PDF/JPG/PNG attachment.
- Usage movements may store purpose, recipient/work area and an attachment.
- Movements cannot be edited or deleted after creation.
- Model validation reconciles movement direction with previous and new balances.

### Exact stock addition

- Match identity remains Project + normalized material + normalized supplier + normalized supplier phone.
- Exact matches increase the existing record.
- Unmatched identities create a new record and its first addition in one database transaction.
- Storekeepers cannot create an empty zero-history record from the workspace; the legacy creation URL redirects to Add stock.
- Similar material/supplier matches with a different phone require confirmation.
- Unit mismatches are blocked rather than silently combining incompatible quantities.
- The project row is locked while resolving a new identity to avoid concurrent duplicate creation.
- Latest addition date is updated on every addition.
- Latest known unit price is preserved when a later receipt omits price.

### Stock usage and adjustments

- Usage locks the selected stock record before validating quantity.
- Negative stock is blocked in the form, service and database layers.
- Positive and negative adjustments require a reason.
- All operations update the cached stock balance and create a permanent movement atomically.

### Idempotency and concurrency

- Every form includes a UUID idempotency key.
- Repeated submission returns the original movement without applying the balance change again.
- `transaction.atomic()` and `select_for_update()` serialize changes to the same stock record.
- If movement creation fails, all database changes roll back and a newly written attachment is cleaned up.

### Administrator corrections

- Opening stock is restricted to inventory administrators and only before the first movement.
- Reversal is restricted at both view and service layers.
- A reversal creates an opposite movement and never changes/deletes the original.
- A movement can be reversed only once.
- A reversal cannot be dated before the original movement.
- Reversing an inbound movement is blocked if it would make current stock negative.
- Latest purchase metadata is recalculated from remaining unreversed additions.

### Operational interface

- Live dashboard counters and recent movements.
- Add-stock form with exact/similar matching and balance preview.
- Use-stock form with live available-balance preview.
- Adjustment form on stock details.
- Global stock activity list and movement details.
- Stock-detail movement history.
- Authenticated movement-attachment downloads.
- Administrator-only reversal form.
- Django admin movement screens are read-only and link to the safe reversal workflow.

## Deliberately deferred

- Upgrade 4 completes every remaining approved storekeeper prototype interaction with real data.
- Upgrade 5 adds full date presets, advanced filters, saved views and URL-persisted search state.
- Upgrade 6 adds exact filtered-result XLSX/CSV export and Excel migration workflows.
