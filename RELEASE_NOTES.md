# SESCCO IMS 1.0.21

- Makes Payroll register search production-safe with a shared debounced search contract, cursor/focus preservation after route redraws, and consistent Reset behavior across Internal Company, Rental Manpower, financial, document, and reporting screens.
- Adds accessible, keyboard-operable sorting to Payroll data tables. Sort direction is retained per workspace/route/table, numeric/currency/date values sort naturally, and timesheet editing grids remain excluded from generic row sorting.
- Adds explicit sort controls for Branches & Offices and Departments, including code/name/headcount ordering and persisted sort preference.
- Replaces remaining placeholder workforce filters with working project/supplier worker filters for status, supplier/project, trade, and search; active filter counts and clear/reset actions are shown in the UI.
- Keeps the Projects and Manpower Suppliers advanced filters functional for client/manager/supplier, project/payment terms/workforce/payable, with faster one-pass workforce indexes for large master lists.
- Adds a shared Django list-query contract with allow-listed sort fields, validated asc/desc direction, deterministic ordering, optional bounded pagination, and response metadata for Internal Payroll and Rental Manpower master APIs.
- Expands server-side master search coverage to organization names/codes, supplier contact/address/payment data, and rental worker assignment trade/project fields so API search matches the production UI more closely.
- Extends the Payroll frontend verification contract so non-functional filter placeholders, missing search wiring, missing sortable-table activation, or missing backend list-control hooks fail release verification.
- No database schema, payroll calculation formula, timesheet approval rule, supplier-settlement lifecycle, payment lifecycle, tenant boundary, or authorization model is changed.
