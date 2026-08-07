# Upgrade 6 — exact exports and controlled Excel imports

Upgrade 6 completes the system's data exchange layer without changing the inventory identity or balance rules established in earlier upgrades.

## Exact filtered-result exports

The following screens now export their complete filtered queryset:

- Inventory Explorer
- Low Stock
- Stock Activity
- Stock Details history
- Project Details inventory

Each screen supports Excel (`.xlsx`) and CSV. Export scope is derived from the same server-side forms, filters, date ranges, sorting, visible columns, and permission checks used by the page. Pagination affects only the browser table; it never limits the exported rows.

Excel workbooks contain:

1. `Results` — every matching row in the current sort order and selected columns.
2. `Export Information` — user, timestamp, dataset, scope, filters, sorting, columns, and matching-row count.

CSV exports use UTF-8 with a byte-order mark for reliable Excel opening. Text that could be interpreted as a spreadsheet formula is neutralized before export.

Every export creates a read-only `ExportAudit` record in Django admin.

## Existing workbook migration

Administrators can upload the client's XLSX/XLSM workbook. The importer:

- prefers the `Database` sheet;
- locates supported headers rather than relying on fixed cell positions;
- accepts Excel date cells, serial dates, and common date strings;
- preserves supplier phones as text and warns when Excel stored a phone as a number;
- assigns all rows to one selected active project;
- applies a selected default unit because the old workbook has no unit column;
- uses Project + Material + Supplier + Supplier phone matching;
- previews exact updates, new records, similar-phone warnings, duplicate workbook rows, and invalid rows;
- never changes current quantity;
- creates zero-balance stock records for unmatched legacy rows;
- updates matching description, location, and newer latest-price/date metadata only when enabled.

## Opening-stock import

Administrators can download a validated opening-stock template containing project and unit dropdowns. Opening-stock imports:

- validate every project, unit, identity, quantity, price, minimum, and date;
- reject future dates, non-positive quantities, unit conflicts, duplicate identities, archived stock, and records that already have movement history;
- create proper immutable `Opening stock` movements;
- apply supplied description, location, and minimum quantity to an empty exact match before opening it;
- use deterministic idempotency keys per job row;
- create new stock records only when no exact identity exists;
- require explicit confirmation for similar-phone rows.

## Atomic confirmation

Import confirmation is one database transaction. If any eligible row fails during confirmation, all stock-record and movement changes are rolled back. The job is marked failed with a clear error; no partial inventory remains.

## Administrator controls

The custom workspace provides:

- import history;
- legacy workbook upload;
- opening-stock upload;
- opening-stock template download;
- paginated row preview;
- source workbook download;
- atomic confirmation.

Django admin exposes read-only import rows, import jobs, and export audits. Storekeepers can export their filtered working data but cannot access import controls.
