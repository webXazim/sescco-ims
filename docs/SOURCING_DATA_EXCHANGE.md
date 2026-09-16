# SESCCO MS 1.0.117 — Sourcing Data Exchange

This release adds controlled bulk import/export for the independent Sourcing Directory only.

## Supported datasets

- `vendors` — Sourcing Vendor master, keyed by `code`.
- `materials` — Sourcing Material master, keyed by `code`.
- `vendor_catalog` — Vendor supply references, keyed by `vendor_code + material_code`.
- `manpower_suppliers` — Sourcing Manpower Supplier master, keyed by `code`.
- `trades` — Worker Type / Trade master, keyed by `code`.
- `workforce_catalog` — Workforce capability references, keyed by `supplier_code + trade_code`.

CSV and XLSX are accepted. Files are limited to 2 MB and 5,000 data rows. Imports are all-or-nothing. Use **Validate only** first: the complete import executes inside a rollback-only transaction so uniqueness, model validation, and service-level rules are exercised without persisting changes.

Catalog imports may set `verified_now=yes` plus `contact_name` and `verification_note`. That is the supported bulk-verification mechanism and writes through the same immutable Sourcing revision/audit services as the interactive Verify flow.

Missing Vendor/Material/Supplier/Trade references are rejected. Import never creates operational Inventory suppliers/items, Rental Payroll suppliers/workers, assignments, timesheets, settlement rates, Projects or Accounting transactions.

## Access authority

Import uses the existing edit authority for the dataset: Vendor imports/catalog require `sourcing.vendors.manage`; Manpower Supplier/workforce imports require `sourcing.manpower.manage`; Material/Trade imports require `sourcing.masters.manage`.

Export requires `sourcing.export.execute` **and** matching view permission for the dataset. This prevents the export flag from becoming a backdoor into Vendor, Manpower, or Master data.

Every successful committed import batch records `sourcing.data_import.completed`. Every export records `sourcing.data_exported`. Exported text cells beginning with spreadsheet formula prefixes are neutralized before CSV/XLSX generation.
