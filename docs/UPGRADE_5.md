# Upgrade 5 — Advanced search, date filters, and saved views

This upgrade turns the inventory and movement pages into server-side explorers while keeping the approved clean storekeeper interface.

## Completed

### Inventory Explorer

- Search terms are combined with `AND`; every term may match any indexed inventory field.
- Project, project status, record status, material, description, supplier, normalized phone, supplier location, unit, stock status, creator, and updater filters.
- Quantity, configured minimum, and latest-price ranges.
- Date filtering by latest addition, record creation, or last update.
- Date presets: today, yesterday, this week, last 7 days, this month, last 30 days, this quarter, this year, previous year, and custom inclusive ranges.
- Sorting by project, material, supplier, quantity, minimum, price, creation, update, and addition date.
- User-selectable visible columns.
- Active filter chips with one-click removal.
- URL-persisted state and server-side pagination.

### Stock activity explorer

- Search historical identity snapshots as well as current stock metadata.
- Filter by one or more projects and movement types.
- Material, supplier, normalized phone, reference, purpose, recipient, reason, user, quantity, price, and date filters.
- Date presets and custom inclusive ranges.
- User-selectable columns and sorting.
- Historical supplier names and phone numbers remain searchable after stock metadata changes.

### Stock details

- Movement history now supports search, action filters, user filters, date presets, custom ranges, and sorting.
- Pagination preserves the complete filter state.

### Low stock

- The low-stock page remains permanently scoped to active low/out-of-stock records.
- It now supports project, material, supplier, phone, unit, quantity, minimum, date, sorting, and visible-column filters.

### Saved views

- A storekeeper can save the current Inventory, Activity, or Low Stock filter state.
- Saved views store only whitelisted query parameters, not copied inventory data.
- Filters, sorting, and visible columns are restored from the URL.
- Saved views are private to their owner.
- Storekeepers can open, rename, and delete their own saved views.
- Pagination parameters and unknown/tampered fields are never stored.

### Database and performance

- Added indexes for normalized material names, quantities, latest prices, update dates, movement users/dates, movement prices, and project snapshots.
- Filtering remains entirely server-side; the browser never receives the full dataset for client-side filtering.

## Deliberately deferred to Upgrade 6

- XLSX and CSV export of the exact filtered queryset.
- Export metadata sheets.
- Existing workbook migration preview and opening-stock import.
- Administrator import controls.
