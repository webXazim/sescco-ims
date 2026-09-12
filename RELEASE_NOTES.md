# 1.0.27 — Payroll reference output parity

- Salary slips now snapshot payment method/status/reference, render net salary in words, and use the reference-style Employee / Manager signature layout.
- Company settings support private PNG/JPEG/WebP logo, A4 letterhead and watermark uploads; finalized documents snapshot the storage identity so later branding changes do not rewrite historical outputs.
- Payroll bootstrap now includes all company legal/document identity fields and branding state on a fresh page load.
- `--seed` creates safe synthetic company identity + branding fixtures in addition to the Internal/Rental payroll test populations.
- Added regression/verifier coverage for branding privacy, reference salary output fields and amount-in-words conversion.

# SESCCO IMS 1.0.26

- Converts the supplied company payroll reference documents into explicit production contracts instead of leaving them as spreadsheet-only knowledge.
- Extends Internal Employee masters with a managed address field and carries the address into immutable salary-payment snapshots, search, API payloads and WPS readiness.
- Expands configurable Bank/WPS templates so bank-owned layouts may omit the internal employee number when the external contract identifies rows by bank account / Iqama; Net Salary remains mandatory.
- Adds the source-compatible WPS column shape: Bank, Account Number, Total Salary, Transaction Reference, Employee Name, National ID/Iqama ID, Employee Address, Basic Salary, Housing Allowance, Other Earnings and Deductions.
- Adds company print identity settings for Commercial Registration, VAT number, document address/email/phone and website, and snapshots them into finalized payroll/manpower documents.
- Upgrades finalized salary slips to render component-level earnings/deductions, employee Iqama/address and the existing immutable payroll snapshot rather than relying on a fixed four-line earnings layout.
- Adds an idempotent `seed_payroll_test_data` management command and wires `scripts/deploy-production.sh --seed` / `scripts/deploy-production-freeze.sh --seed` through the normal post-migration release runner.
- The seed creates 18 DEMO internal employees and 30 RDEMO rental workers, organization masters, salary components, Basic/300 × OT × 1.5 test overtime policy, payment/WPS profiles, supplier/project/assignments, attendance/timesheets, adjustments and a current draft test period.
- On a clean/demo tenant, the seed also builds a previous-month closed lifecycle covering approved payroll, WPS payment reconciliation, salary slips/receipts, locked rental timesheet, supplier settlement/invoice/payment/receipt and closed settlement history.
- Seeded bank accounts, Iqama/IDs, phone numbers and references are synthetic DEMO data; uploaded production bank/identity values are not copied into source code or fixtures.
- Adds regression coverage for company document identity settings, the source-compatible WPS layout without an internal employee-number column, synthetic Saudi IBAN generation, and Internal/Rental seed population counts.
- Adds a release-time `verify-payroll-reference-coverage.py` gate and includes it in the production-freeze verifier.
- No real payroll history is auto-approved by the seed: closed-history generation is skipped when non-DEMO Internal or Rental worker masters already exist.

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
