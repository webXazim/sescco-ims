# SESCCO IMS 1.0.25

- Fixes the Internal Payroll card-height regression visible on Salary Payments and Bank & WPS Export.
- Reduces the no-payment-batch empty state from the old 300px prototype minimum to a compact 116px production state, while preserving the same message, icon and Bank/WPS action.
- Fixes the oversized Bank/WPS `Export template` launcher at its actual source: `.bank-template-picker` was incorrectly normalized as a row toolbar, so the shared `flex-basis: 220px` became vertical height inside its column layout.
- Removes `.bank-template-picker` from row-toolbar normalization and normalizes only its native select. The picker now uses an explicit two-row label/control grid with a 42px launcher and no vertical flex sizing.
- Cleans both duplicated Internal Payroll V2 payment-empty rules (`pages/payroll.css` and the PRS execution cutover) so an older imported rule cannot restore the 300px height later in the cascade.
- Keeps the final Payroll control stylesheet as the single authority for operational select geometry; no new broad `!important` card-height patch was added.
- Extends release verification to reject putting the Bank/WPS template picker back into the generic toolbar selector and to enforce the compact Internal Payments empty-state height.
- Updates the final Payroll control asset cache-buster to `1.0.25`.
- No payroll calculations, attendance logic, salary-payment workflow, Bank/WPS data generation, APIs, database schema, permissions, authorization or tenant isolation are changed.
