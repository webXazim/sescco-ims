# SESCCO IMS 1.0.129 — Inventory quantity integrity, sorting and wheel guard

Base: Project Pulse Execution Schedule v1.0.128 full source.

## Behavior

- Countable units such as pc, pcs, each, laptop, set, bag, carton and box are integer-only for new inventory operations even where legacy unit records were accidentally marked as allowing decimals. Continuous/measured units such as kg, m, m², m³ and litres remain fractional when configured as such.
- Back-end protections apply to additions, issue/use, adjustments, transfers, staged project approvals, Excel import, unit changes, and minimum quantities. Client-side form steps adjust to the selected unit.
- Data migration `inventory.0020_enforce_countable_units` fixes legacy unit flags only. **No historical movement, price or live stock quantity is rounded or rewritten automatically.** Fractional legacy balances may remain and block new movements until physically reconciled.
- The command `python manage.py audit_quantity_units` is read-only. To correct an individual legacy countable balance, use `python manage.py reconcile_countable_balance --reference <UUID> --target <WHOLE> --reason <PHYSICAL_COUNT_REASON>` as a dry run; add `--apply --confirm-reference <UUID> --actor-username <APPROVED_USER>` only after physical verification and an approved backup. This records an immutable corrective movement.
- Quantity display removes unnecessary trailing zeros. Old fractional movements are retained/displayed for audit.
- The global wheel guard prevents unintentional value changes when scrolling over focused number/date/time/select fields across Inventory, Administration, Sourcing, Payroll, and Project Pulse. Keyboard editing and button controls remain functional.
- Inventory Explorer and Office Stock default to `Recently added first` by **stock-record creation time** (`created_at`, newest-first); `Oldest added first`, recent/oldest update, alphabetical and quantity sorting are also offered. Separate latest-stock-receipt sorting remains available, distinct from record creation. The sort selector is visible and labelled; changing it refreshes the list, preserving filters and pagination rules.
- Inventory CSV/XLSX export uses the same default and explicitly selected sorting as the listing.

## Security / rollback

- No cross-company or role privilege changes. No Inventory/Payroll/Project Pulse financial integration added.
- Backup database, media and private attachments before migration; test on staging.
- New Django migration is forward-only (safe operation changes unit flags); do not attempt to roll back manually by restoring old flags. Keep audit history intact.

## Validation

Offline: `python scripts/verify-inventory-quantity-and-sorting.py`, `bash scripts/verify-production-freeze.sh`, `node --check static/platform/js/prevent-wheel-value-changes.js`.

Runtime (must run on staging): `python manage.py migrate`, `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py test apps.inventory apps.data_exchange` (as applicable) before production rollout.
