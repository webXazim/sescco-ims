# SESCCO IMS 1.0.24

- Rebuilds the Payroll dropdown/control CSS boundary instead of adding another override patch. `static/platform/css/select-controls.css` is now a cross-application baseline only, while `static/payroll/css/v2/payroll-controls.css` is the single final Payroll authority loaded last.
- Fixes the Supplier Payments `All suppliers` launcher with an explicit 42px production height, readable 13px text, normal chevron/padding and a bounded 220–320px desktop width instead of the thin full-row control shown in production.
- Removes obsolete Supplier Payments toolbar geometry from legacy `components.css`, `responsive.css` and `production-polish.css`, eliminating the competing declarations that were overriding previous refinements.
- Normalizes Internal and Rental Payroll business-filter selects after every render: legacy `compact-select` classes are removed from operational filters and only genuine timesheet day/page-size/table editors retain dense sizing.
- Covers normal register/filter toolbars, Payroll Run controls, Salary Setup, Salary Payments, Bank/WPS, Advances & Adjustments, Documents, Reports, Rental workforce/assignment filters, settlement/payment filters, management audit filters and advanced Project/Supplier filters.
- Adds a semantic CSS fallback for normalized Payroll toolbars so 42px control geometry does not depend on per-select class timing.
- Keeps dense attendance/timesheet controls intentionally compact and leaves form/drawer/table-cell editors outside the operational launcher contract.
- Adds a versioned `?v=1.0.24` final Payroll control stylesheet reference so a stale browser/CDN copy cannot mask this CSS reset after deployment/collectstatic.
- Extends release verification to enforce final stylesheet load order and reject reintroduction of Supplier Payments toolbar geometry into legacy CSS files.
- No payroll calculations, attendance logic, settlements, payment lifecycle, API behavior, database schema, permissions, authorization or tenant isolation are changed.
