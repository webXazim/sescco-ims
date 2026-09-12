# 1.0.37 — Branding migration-state repair

- Fixes the production pre-deployment `makemigrations --check --dry-run` failure introduced by a serialization-shape mismatch in the company document-branding file-extension validator.
- Makes the live `CompanySettings` model use the same keyword-form `FileExtensionValidator(allowed_extensions=...)` constructor already frozen in migration `core.0003_company_document_branding`.
- Prevents Django from proposing the schema-no-op `0004_alter_companysettings_document_letterhead_and_more` migration for logo, letterhead and watermark fields.
- Does not add or apply a new database migration and does not modify existing company branding data.
- The `security.W021` HSTS preload message remains a non-blocking deployment warning; this patch does not opt the domain into browser preload policy automatically.

# 1.0.36 — Lifecycle retention governance

- Adds a machine-readable lifecycle/retention contract covering all 58 persisted SESCCO MS models so every new model must declare how it may leave active use.
- Freezes the rule that real master data uses Archive / Restore / guarded Delete-unused while operational history uses workflow states, effective dating, reversal or immutability instead of generic destructive actions.
- Explicitly classifies system users and memberships as deactivate/reactivate-only, company/settings/policies as retained singletons, and saved views/preferences as ordinary user-owned disposable data.
- Keeps Internal Payroll salary structures effective-dated and changes the UI action from misleading “Edit” to “Create effective change”; historical structures are retained rather than archived or deleted.
- Clarifies that the company payroll proration policy is retained singleton configuration and that changing it only affects future calculations.
- Adds `verify-lifecycle-retention-contract.py` to the production-freeze gate; it fails if a persisted SESCCO model is added without a retention classification or if key lifecycle safeguards regress.
- Adds `docs/LIFECYCLE_RETENTION.md` and `merge/lifecycle-retention-contract.json` as the operator/developer authority for Archive, Delete-unused, effective-dated, workflow and immutable record behavior.
- No historical payroll, attendance, rental, inventory, audit or finalized document data is rewritten or removed by this upgrade.

# 1.0.35 — Unified lifecycle UX

- Converged Internal Payroll, Rental Manpower, Projects and Inventory master records onto one consistent Actions-menu pattern for edit, lifecycle, archive/restore and guarded delete-unused operations.
- Added shared Payroll lifecycle menu/panel/error styling plus shared Inventory/Project lifecycle-action styling, with destructive delete actions visually separated from archive/restore.
- Lifecycle drawers now explain archive versus permanent delete and show backend dependency blockers inline instead of relying on transient toast messages alone.
- Fixed the Payroll drawer save gate so organization, rental-master and configuration lifecycle actions are accepted by the shared save path.
- Kept lifecycle enforcement server-authoritative: archive preserves real history; permanent deletion remains available only for unused records that pass dependency checks.

# 1.0.34 — Secondary configuration lifecycle

- Added lifecycle authority for Internal Payroll salary components, overtime policies and bank/WPS export templates.
- Added Archive / Restore-as-Inactive / Delete-unused actions with required archive reasons, typed delete confirmation and append-only audit events.
- Protected historical salary structures, overtime references and salary-payment batches from destructive master-data deletion.
- Archived salary components, overtime policies and export templates are excluded from new salary structures, OT assignments and payment batches while historical snapshots remain readable.
- Added guarded Delete-unused for employee payment profiles; profiles with salary-payment history must be made Inactive instead.
- Kept company salary-payment settings permanent and kept system users on the existing deactivate/reactivate-only policy so audit actor history is retained.
- Added Archived filtering and lifecycle controls in Salary Setup and Bank/WPS template UI, plus release verification and migration `0010_secondary_configuration_lifecycle`.

# 1.0.33 — Projects + Inventory master lifecycle

- Applies the central lifecycle authority to shared Projects and Inventory Units, Material Suppliers, Stock Records and Office Inventory Locations.
- Separates Archive from 30-day Trash: Archive preserves valid historical masters, while Trash is limited to unused records created by mistake.
- Blocks project archive while positive stock or open/future Rental Manpower assignments remain, and blocks Delete-unused after Inventory or Rental history exists.
- Keeps archived masters resolvable in historical Inventory/Payroll records while excluding them from new operational selectors.
- Synchronizes each project-owned Inventory Location to the shared Project lifecycle instead of allowing a second conflicting lifecycle.
- Prevents stock transfers from silently reactivating archived destination stock and requires an explicit Restore.
- Prevents archived material suppliers and units from being reused in new stock activity until explicitly restored.
- Adds lifecycle-safe Office Inventory support for multiple SESCCO branches/offices and a dedicated Inventory Locations workspace.
- Extends Trash, Archive, audit, release verification and frozen migration manifests for the new master-data lifecycle.

# 1.0.32 — Rental Manpower supplier / worker lifecycle

- Adds central-authority Archive / Restore / Delete-unused lifecycle to Manpower Suppliers and Rental Workers.
- Adds effective worker inactive date/reason and archive metadata without rewriting assignment history.
- Blocks supplier archive/deactivation while active workers remain and blocks hard delete after worker, settlement, adjustment or payment history exists.
- Blocks worker inactivation/archive while current or scheduled assignments remain and blocks hard delete after assignment/timesheet/adjustment/settlement history exists.
- Restored suppliers/workers return as Inactive and must be deliberately reactivated.
- Archived records remain visible for historical profiles but are excluded from new operational supplier/worker selection.
- Adds lifecycle controls and Archived filters to the Rental Manpower UI.

# 1.0.31 — Branch / Office + Department lifecycle

- Adds explicit Branch vs Office classification without splitting organization history.
- Adds Archive / Restore / Delete-unused lifecycle for branches/offices and departments through the central lifecycle authority.
- Blocks archive/deactivation while current employed workers still use the master and blocks hard delete once assignment/payroll history exists.
- Archived masters remain resolvable in historical employee/payroll context but disappear from new-assignment selectors.
- Restored organization masters return as Inactive and must be deliberately reactivated.
- Adds Active / Inactive / Archived / All register filters and lifecycle drawers in Internal Payroll.
- Prevents an inactive employee from returning to payroll eligibility while their current branch/department is archived or inactive.

# 1.0.30 — Central lifecycle authority

- Adds one shared backend lifecycle authority for master-data Archive, Restore, Delete and Deactivate decisions across SESCCO MS.
- Standardizes `can_archive`, `can_restore`, `can_delete`, `delete_blockers`, `can_deactivate` and `archive_reason_required` behind registered module policies instead of page-specific rules.
- Adds structured blocker codes/messages/counts, confirmation-token handling and operation reason requirements while keeping permissions in the owning module services.
- Standardizes lifecycle audit metadata with lifecycle action/policy, reason and dependency counts on the existing immutable `AuditEvent` ledger.
- Migrates the Internal Employee archive/deactivate/restore/delete safeguards onto the central authority as the reference implementation without changing its user-facing lifecycle semantics.
- Exposes employee lifecycle capabilities separately from register serialization so profile/action surfaces can consume authoritative state without introducing N+1 blocker queries on employee lists.
- Adds central lifecycle regression tests and a production-freeze verifier; no database migration or historical-data rewrite is required.

# 1.0.29 — SESCCO MS single-company foundation

- Rebrands the private deployment as **SESCCO MS — Management System** using the supplied SESCCO mark across Inventory, Payroll, authentication and error surfaces.
- Introduces explicit single-company mode while preserving the existing company foreign-key/security boundary internally.
- Removes the production company switcher from the shell and keeps only authorized module/workspace switching.
- Adds production checks for exactly one active company and optional primary-company slug pinning.
- Rewords platform navigation from SaaS-oriented “business area” terminology to private-system “module” terminology.

# SESCCO IMS 1.0.28

- Adds a production employee-employment lifecycle to Internal Payroll instead of treating status as a normal editable profile field.
- Adds explicit Active, On Leave, Inactive and Terminated transitions with audited reasons; termination requires an employment end date and closes the open branch/department assignment at that date.
- Adds Archive / Restore Archive for stopped employee masters. Archived records are removed from the default current-employee register but remain available through the Archived filter with all historical payroll, attendance, payment and document references retained.
- Adds guarded hard deletion for unused/duplicate onboarding masters only. The operator must type the employee ID, and any attendance, overtime, adjustment, payroll-run, salary-payment or finalized salary-slip history blocks deletion and directs the operator to Archive instead.
- Removes protected employment status/end-date editing from the ordinary Edit Employee drawer and adds a dedicated Employment action with lifecycle guidance.
- Adds lifecycle banners and status visibility on the employee profile, disables organization reassignment while an employee is inactive/terminated/archived, and preserves effective-dated organization history.
- Fixes the Internal Employee profile header spacing at the final Payroll CSS authority layer so the old unlayered `.entity-header` rule can no longer collapse horizontal padding.
- Adds API/service regression coverage for termination, archive filtering, leave audit requirements and guarded unused-master deletion.
- Adds a release-time employee-lifecycle verifier and freezes the new lifecycle migration in the production migration/source manifests.
- No historical payroll, attendance, payment or finalized document snapshot is deleted or rewritten by deactivation, termination or archive.

# SESCCO IMS 1.0.27

- Completes Payroll reference-output parity for salary slips and employee payment documents.
- Adds salary amount in words, paid-by/payment reference presentation and employee/manager signature areas to finalized salary-slip output.
- Adds private company logo, A4 letterhead and watermark assets to Payroll document settings and snapshots branding identity for immutable finalized documents.
- Preserves company legal identity, CR, VAT, address, email, phone and website on generated Payroll/Manpower documents.
- Extends seeded Payroll test data with safe synthetic document-branding fixtures and corresponding release verification.

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
