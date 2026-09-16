# 1.0.115 — Inventory Manager Permission Reconciliation Hotfix

- Fixes the production `merge_access_report --fail-on-errors` stop where the built-in system `role-inventory-manager` profile was missing the already-authoritative `inventory.import.execute` grant.
- Adds forward data migration `accounts.0014_inventory_manager_import_permission`; it targets only active system Inventory Manager profiles and adds the missing grant idempotently.
- Preserves Storekeeper authority unchanged: Storekeeper still cannot import Inventory data.
- Uses `schema_editor.connection.alias` for migration-time ORM operations and does not manually edit or fake migration history.
- Makes no database schema, permission-catalog, Payroll formula, Inventory quantity, Sourcing business-rule, membership, scope or operational-integration change.
- Keeps `python manage.py merge_access_report --fail-on-errors` as the authoritative runtime reconciliation gate; after migration, `system_profile_permission_drift` must be empty.
- Carries forward the 1.0.112 index-name, 1.0.113 Sourcing migration-state, and 1.0.114 Accounts historical-migration fixes unchanged.
- Binds this hotfix to exact 1.0.114 SHA-256 `2a3d174556821454f1f55013fba26247d2a0dc594f4276fe6aecdb3b7b07ecfb`.

# 1.0.114 — Accounts Rental Supervisor Migration Hotfix

- Fixes the production migration failure in `accounts.0008_rental_supervisor_profile` where historical migration code incorrectly requested `accounts.Company`; the authoritative Company model is `core.Company`.
- Corrects the historical `RunPython` migration to resolve `Company` from the `core` app and to use `schema_editor.connection.alias` for all migration-time reads/writes.
- Does not fake, skip, or replace `accounts.0008`; the failed PostgreSQL migration can be rerun normally after deploying this release.
- Adds a dedicated static verifier that rejects the invalid `accounts.Company` lookup and requires the historical Core Company dependency to remain present through the Accounts migration chain.
- Carries forward the 1.0.112 index-name fix and 1.0.113 Sourcing migration-state alignment unchanged.
- Makes no model/schema, Payroll formula, Inventory quantity, permission-catalog, Sourcing business-rule, or operational-integration change in this release.
- Binds this hotfix to exact 1.0.113 SHA-256 `aa870514601cb796a1f58bd569acd0c527082c411494b07dbcba830ba25a6a41`.

# 1.0.113 — Sourcing Migration State Drift Hotfix

- Fixes the production `makemigrations --check --dry-run` failure where Django proposed `sourcing.0008` with 13 pending `AlterField` operations.
- Aligns the migration state of 11 Sourcing `company` ForeignKeys with the inherited `CompanyOwnedModel` placeholder `related_name="%(app_label)s_%(class)s_records"`.
- Aligns the migration state of `deleted_by` on `SourcingVendor` and `SourcingManpowerSupplier` with `related_name="%(app_label)s_%(class)s_deleted_records"`.
- Adds forward migration `sourcing.0008_align_abstract_relation_state`; the operations are migration-state alignment only and do not change database data, columns, indexes, Payroll formulas, Inventory quantities, permissions, or Sourcing business rules.
- Keeps the 1.0.112 index-name deployment hotfix intact and adds a dedicated migration-state verifier.
- Keeps `python manage.py makemigrations --check --dry-run` as the authoritative runtime drift gate.
- Binds this hotfix to exact 1.0.112 SHA-256 `5a3c71f2b0fb1cc065beaadc5ec6eb8846d8834bf12389de55e78f37dc7d9fdb`.

# 1.0.112 — Django Index Name Deployment Hotfix

- Fixes the production `SystemCheckError` / `models.E034` raised by two explicit Django model index names longer than 30 characters.
- Renames `acct_profile_company_active_idx` to `acct_prof_company_active_idx` on `accounts.AccessProfile`.
- Renames `src_mpcontact_supplier_active_idx` to `src_mpc_supplier_active_idx` on `sourcing.SourcingManpowerContact`.
- Preserves historical migrations and adds forward `RenameIndex` migrations `accounts.0013` and `sourcing.0007`, making the hotfix safe for both fresh and already-migrated databases.
- Adds a dedicated static index-name verifier and keeps `python manage.py check --deploy --fail-level ERROR` as the authoritative runtime deployment gate.
- Makes no Payroll formula, Inventory quantity, Sourcing permission/business-rule, tenant-isolation, or operational-module integration change.
- Binds this hotfix to exact 1.0.111 SHA-256 `7662aaf89be46014b077bdd7e0178679dfbd1559cf901b262b6c2989386fbb53`.

# 1.0.111 — Sourcing Browser E2E + Production Freeze

- Finalizes the Sourcing Directory feature set with a live Chromium certification runner covering the complete Vendor and Manpower sourcing journeys; no schema, permission-catalog, Payroll formula or Inventory quantity formula change is introduced.
- Certifies Vendor Directory → Supply Catalog → Material Finder → Verification History → Verify now → immutable history evidence using deterministic benchmark `SDEMO-*` fixtures.
- Certifies Manpower Supplier Directory → Workforce Catalog → Workforce Finder → Verification History → Verify now → immutable history evidence using the same bounded server-authoritative workflow.
- Enforces a maximum of 100 rendered business rows, the existing 350 ms Finder debounce, stale-request cancellation, final-query preservation, same-origin 5xx detection, uncaught browser-error detection and a 10-second per-scenario settle budget.
- The live runner never creates/deletes Sourcing masters. Its only write is a verification revision on seeded Sourcing reference rows; the 1.0.110 runtime security suite remains authoritative proof of zero operational-module mutation.
- Adds `scripts/certify-sourcing-browser-e2e.py`, `scripts/verify-sourcing-browser-e2e.py`, `apps.sourcing.tests.test_browser_e2e_freeze`, `merge/sourcing-browser-e2e-production-freeze.json`, and `docs/SOURCING_BROWSER_E2E.md`.
- Makes the Sourcing browser gate mandatory in the release candidate and production freeze, while preserving all 1.0.110 security/tenant/cross-module certification requirements.
- Binds this release to exact predecessor 1.0.110 SHA-256 `bf498e6af3405b279cb42fbbf769c5baeb14d8940d59b3f732e89950dd503b2b`.

# 1.0.110 — Sourcing Security, Tenant & Cross-module Isolation Certification

- Adds a focused production certification suite for the independent Sourcing Directory; no database migration, permission-catalog expansion, Payroll formula change or Inventory quantity change is introduced.
- Certifies Vendor-only versus Manpower-only authority in both directions and confirms Reference Master edit authority remains separate.
- Certifies Company A / Company B tenant isolation through the real company-context middleware and company-scoped Sourcing object lookups.
- Certifies direct backend POST denial for View-only users across Vendor, Manpower, Material/Trade master and verification endpoints; rejected requests leave Sourcing rows and immutable revision counts unchanged.
- Certifies Material Finder and Workforce Finder never return archived or trashed sources and continue to require active parent/reference rows.
- Certifies Vendor and Workforce verification revisions remain append-only through queryset and instance mutation guards.
- Certifies Sourcing Access Profile edits increment assigned users' `security_version` and revoke stale authenticated sessions on the next request.
- Adds runtime zero-mutation evidence across every installed operational app model while Sourcing create/verify services execute; Inventory, Projects, Internal Payroll, Rental Manpower, Documents and Data Exchange row counts must remain unchanged, with future standalone Accounting automatically included if installed.
- Adds `merge/sourcing-security-certification.json`, `docs/SOURCING_SECURITY_CERTIFICATION.md`, `scripts/verify-sourcing-security-certification.py`, and `apps.sourcing.tests.test_security_certification` as mandatory release gates.
- Binds this release to exact 1.0.109 predecessor SHA-256 `4de083b4bf99c38672548b9ccbe7b0ef2a66f9d0a461af34ffde21b295d0c1a2`.

# 1.0.109 — Sourcing Scale Hardening & Benchmarking

- Adds deterministic Sourcing `functional`, `realistic`, and `benchmark` seed profiles. Benchmark volume is frozen at 10,000 Vendors, 2,000 Materials, 50,000 Vendor offers, 5,000 Manpower Suppliers, 250 Trades, and 25,000 Workforce offers.
- Adds `seed_sourcing_test_data` with the `SDEMO-` namespace, restart-safe `bulk_create(ignore_conflicts=True)`, mixed-company protection, and direct integration into `deploy-production.sh --seed` / release tasks.
- Replaces Vendor and Manpower directory multi-join `DISTINCT` aggregation with correlated count subqueries and `EXISTS` contact matching, avoiding high-cardinality join fanout.
- Adds additive Sourcing-only composite indexes for active Material/Trade, supplier/vendor, availability, and verification-freshness paths via migration `sourcing.0006_scale_finder_indexes`.
- Makes Vendor Supply Catalog and Manpower Workforce profile tables server-paged at 25/50/100 rows instead of hydrating every capability row into the browser.
- Adds progressive Finder request hardening: 350 ms debounce, `AbortController` cancellation of stale requests, bounded DOM replacement, and full GET fallback when JavaScript is unavailable.
- Adds `sourcing_scale_report` with query/time budgets across all Sourcing directories, both Finders, profile catalogs, and the 5,000-row import parser.
- Adds focused scale regressions, `merge/sourcing-scale-hardening.json`, `docs/SOURCING_SCALE_HARDENING.md`, and mandatory static/runtime/benchmark release gates.
- Keeps Sourcing reference-only; no Inventory quantity, Rental Payroll worker/rate, Project, or Accounting behavior changes.
- Binds this release to exact 1.0.108 predecessor SHA-256 `eaf3056bd03657b14cf5bd25230f72718cadef14473d0240c4992f268d8b4784`.

# 1.0.108 — Sourcing Import / Export & Bulk Maintenance

- Adds a dedicated **Sourcing Data Exchange** page for controlled CSV/XLSX bulk maintenance and audited exports across Vendor, Material, Vendor Catalog, Manpower Supplier, Trade and Workforce Catalog datasets.
- Imports are capped at 2 MB / 5,000 data rows, upsert through existing Sourcing services, reject duplicate identities and unknown catalog references, and commit all-or-nothing.
- Adds **Validate only** dry-run authority: the complete import executes inside a rollback-only transaction so model uniqueness, service validation and row-level errors are exercised without changing data.
- Catalog imports support controlled bulk verification through `verified_now=yes`, `contact_name` and `verification_note`, reusing immutable Vendor/Workforce revision and audit paths.
- Export requires `sourcing.export.execute` plus matching dataset view permission, supports CSV/XLSX and current-view filters, records `sourcing.data_exported`, and neutralizes spreadsheet-formula prefixes in exported text.
- Import authority remains the existing edit boundary: Vendor, Manpower and Reference Master imports cannot cross-grant one another. Successful committed batches record `sourcing.data_import.completed`.
- Keeps the module strictly reference-only: no Inventory stock/supplier, Rental Payroll worker/supplier, assignment, timesheet, settlement, Project or Accounting record is created or changed.
- Adds `merge/sourcing-data-exchange.json`, `docs/SOURCING_DATA_EXCHANGE.md`, focused runtime regressions and a mandatory static/runtime release gate. No database migration or Payroll/Inventory formula change.
- Binds this release to exact 1.0.107 predecessor SHA-256 `ca590378d85bf74bbad4c6fb0b77ea7265be4bff53d2ce2593c47ce027fa0c4c`.

# 1.0.107 — Workforce Finder & Verification History

- Adds a production **Workforce Finder** under the independent Sourcing Directory: search controlled worker type/trade code, name, alias or category first, then compare matching Manpower Suppliers without opening supplier profiles one by one.
- Adds server-side availability, freshness, trade category, supplier, work-location, Hour/Day/Month rate-basis and rate-range filters plus deterministic 25/50/100 pagination and sorting by trade, supplier, quantity, rate, verification time or update time.
- Reuses the company Sourcing freshness policy (`Fresh`, `Needs verification`, `Stale`, `Never verified`) and separately flags expired reference-rate validity so stale commercial information cannot look current.
- Adds **Verify now** from Workforce Finder and supplier Workforce Catalog, limited to sourcing availability/quantity/rate/basis/overtime/validity/mobilization/location fields; captures `Spoke With`, verification note and confirming SESCCO user/time.
- Adds server-paginated immutable **Workforce Verification History** with field-level before → after changes. `sourcing.manpower.view` may inspect history; only `sourcing.manpower.manage` may submit verification.
- Writes `sourcing.workforce_offer.verified`, updates supplier freshness and appends immutable `SourcingWorkforceOfferRevision` evidence on every confirmation, including confirmations with no business-value change.
- Keeps the workflow strictly reference-only: no Rental Manpower supplier/worker, assignment, attendance/timesheet, Payroll/settlement rate, Inventory or Accounting record is created or changed.
- Adds focused regressions, `merge/sourcing-workforce-finder.json`, `docs/SOURCING_WORKFORCE_FINDER.md`, and a mandatory static/runtime release gate. No database migration or Payroll/Inventory formula change.
- Binds this release to exact 1.0.106 predecessor SHA-256 `3be72bcc9edc38b95cab475d31d5b4b1e500685f579b62c88d9f82d1df642365`.

# 1.0.106 — Worker Trade Master & Workforce Catalog

- Activates the independent **Worker Types / Trades** Sourcing reference master with company-scoped code/name/category, controlled aliases, Active/Inactive lifecycle, server-side search and bounded 25/50/100 pagination.
- Adds normalized trade-alias search/collision protection so equivalent terms such as AC Technician / A/C Technician can resolve to one canonical Sourcing worker type.
- Activates each Manpower Supplier's **Workforce Catalog** using the existing Sourcing-owned `SourcingWorkforceOffer`: worker type, availability, nullable available quantity, nullable reference rate, Hour/Day/Month basis, optional overtime rate, rate validity, mobilization lead time, work location/coverage and notes.
- Adds `Verified now`, confirming SESCCO user/time, optional contacted-person and verification note capture, supplier freshness updates, immutable `SourcingWorkforceOfferRevision` evidence and Sourcing audit events for every catalog mutation.
- Enforces `sourcing.masters.view/manage` independently for the Trade master and `sourcing.manpower.view/manage` for Workforce Catalog rows; a Manpower Editor may select active Trades without gaining Trade-master edit authority.
- Keeps Sourcing strictly reference-only: no Rental Payroll supplier/worker, assignment, timesheet, settlement, Payroll rate, Inventory or Accounting records are created or changed.
- Adds forward migration `sourcing.0005_trade_alias_search`, focused Trade/Workforce regressions, `merge/sourcing-trade-workforce-catalog.json`, `docs/SOURCING_TRADE_WORKFORCE_CATALOG.md`, and a mandatory release gate.
- Binds this release to exact 1.0.105 predecessor SHA-256 `ab85b97e9fa9f60467799c6c158e950f0d8fb12d0ddb0a6eb493e69e4ab75e0f`.

# 1.0.105 — Manpower Sourcing Master

- Activates the independent **Manpower Suppliers** sourcing directory with server-side search, status filters, deterministic sorting and bounded 25/50/100 pagination.
- Adds company-scoped create/edit/detail screens for sourcing-only manpower suppliers using the existing `SourcingManpowerSupplier` master; no Rental Payroll supplier is created or synchronized.
- Adds `SourcingManpowerContact` for callable contact persons, including one active primary contact per supplier and deactivate-not-destroy contact lifecycle.
- Adds explicit Active/Inactive, reversible Archive and reversible 30-day Trash lifecycle. Trash requires exact supplier-code confirmation and a reason.
- Records immutable `AuditArea.SOURCING` evidence for supplier master, lifecycle and contact mutations and exposes a bounded Activity timeline.
- Enforces `sourcing.manpower.view` for every read surface and `sourcing.manpower.manage` for every mutation, independent from Vendor, Inventory, Storekeeper, Foreman, Finance and Rental Payroll authority.
- Keeps the Workforce profile tab reference-only in this release; worker type / quantity / rate management remains reserved for Upgrade 1.0.106.
- Adds migration `sourcing.0004_manpower_supplier_contacts`, focused Manpower-master regressions, `merge/sourcing-manpower-master.json`, `docs/SOURCING_MANPOWER_MASTER.md`, and a mandatory release gate.
- Binds this release to exact 1.0.104 predecessor SHA-256 `88220df5d3896cb626a36bfa49ffba25becd1a3ab1c161e158535b149b8fc9cf`.

# 1.0.104 — Vendor Verification & History UX

- Adds a fast **Verify now** workflow from Material Finder and each Vendor Supply Catalog row so sourcing staff can confirm current availability, quantity, unit, minimum order, reference rate, quote validity and lead time without reopening the full offer editor.
- Captures the Vendor person contacted plus a verification note, stamps the confirming SESCCO user/time, updates the current Sourcing reference snapshot and advances Vendor freshness.
- Appends immutable `SourcingVendorOfferRevision` evidence on every confirmation, including calls where the business values did not change, and writes `sourcing.vendor_offer.verified` to the Sourcing audit ledger.
- Adds a server-paginated 25/50/100 **Verification History** available to Vendor viewers, with field-level before → after differences and contacted-person/note evidence.
- Keeps mutation authority at `sourcing.vendors.manage`; `sourcing.vendors.view` can inspect history but cannot submit verification directly or through backend endpoints.
- Adds safe return navigation between Finder, Vendor profile, Verify and History while rejecting non-Sourcing redirect targets.
- Keeps the workflow strictly reference-only: no Inventory Supplier/stock, purchase/receiving, Accounting, Payroll, Rental Manpower or Project records are created or changed.
- Adds focused Vendor verification regressions, `merge/sourcing-vendor-verification.json`, `docs/SOURCING_VENDOR_VERIFICATION.md`, and a mandatory release gate.
- No database migration, Payroll formula, Inventory quantity formula, or Accounting posting behavior changes.
- Binds this release to exact 1.0.103 predecessor SHA-256 `490c83bdcaab2f4586b973ca5ac78f11051df2429babd5a6c9683c3610516214`.

# 1.0.103 — Material Finder

- Adds a production **Material Finder** under the independent Sourcing Directory: search a material/item first, then compare matching reference Vendors without opening Vendor profiles one by one.
- Searches Sourcing Material code/name/controlled aliases plus offer specification, brand/model and Vendor code/name, with company-scoped server-side filtering and deterministic 25/50/100 pagination.
- Adds Availability, Freshness, Category, Vendor, Location and reference-rate filters, plus sorting by Material, Vendor, rate, quantity, verification time or update time.
- Activates the per-company Sourcing freshness policy: Fresh within the configured window (default 7 days), Needs verification through the configured stale threshold (default 30 days), Stale after that, and Never verified when no confirmation exists.
- Excludes inactive/archived/Trash Vendors, inactive Materials and inactive Vendor offer rows from on-demand Finder results while preserving all underlying reference/history records.
- Enforces `sourcing.vendors.view` on the Finder and only renders Edit reference actions for `sourcing.vendors.manage`. Material Master permission is not required to search controlled material names/aliases.
- Keeps the Finder strictly read-only and reference-only: searching does not create verification history, Inventory stock/suppliers, purchase/receiving records, Accounting entries, Payroll data or Rental Manpower records.
- Adds focused Material Finder regressions, reusable Sourcing freshness authority, `merge/sourcing-material-finder.json`, `docs/SOURCING_MATERIAL_FINDER.md`, and a mandatory release gate.
- No database migration, Payroll formula, Inventory quantity formula, or Accounting posting behavior changes.
- Binds this release to exact 1.0.102 predecessor SHA-256 `b96eb8585a20f52337871b8c04916976399cc3f59604a7ad33d5afe0745270ce`.

# 1.0.102 — Material Master & Vendor Supply Catalog

- Activates the independent Sourcing Material master with company-scoped code/name/category/default-unit management, controlled aliases, Active/Inactive state, server search and bounded 25/50/100 pagination.
- Adds normalized alias search and rejects exact company-local material name/alias collisions so common terms resolve to one controlled Sourcing Material.
- Replaces the Vendor profile Supply Catalog placeholder with production catalog rows for material, specification, brand/model, availability, nullable available quantity, unit, minimum quantity, nullable reference rate, currency, validity date and lead time.
- Adds Vendor Supply Catalog create/edit/activate/deactivate flows under `sourcing.vendors.manage`; Vendor viewers can read catalog rows but cannot mutate them. Material master edits remain separately gated by `sourcing.masters.manage`.
- Adds `Verified now`, verifier identity and optional contact/note capture. Confirmed updates advance Vendor verification time and every catalog mutation writes immutable `SourcingVendorOfferRevision` before/after evidence plus Sourcing audit events.
- Keeps Sourcing strictly reference-only: no catalog quantity changes Inventory on-hand, no catalog rate creates purchase/accounting values, and no Sourcing Material is linked to an Inventory item master.
- Adds forward migration `sourcing.0003_material_alias_search`, focused Material/Catalog regressions, `merge/sourcing-material-catalog.json`, `docs/SOURCING_MATERIAL_CATALOG.md`, and a mandatory release gate.
- Binds this release to exact 1.0.101 predecessor SHA-256 `52ac1adef10a90e066908b21dac78599b0cadd9d8551a4b7c7c8113bc92ad008`.

# 1.0.101 — Vendor Sourcing Master

- Promotes Vendor Sourcing from a permission-only shell into a production reference Vendor directory with server-side search, deterministic sorting, status filters and bounded 25/50/100 pagination.
- Adds company-scoped Vendor create/edit/detail screens with primary contact summary, phone/email, city/region, CR/VAT, website and sourcing notes.
- Adds `SourcingVendorContact` for additional contact persons, with one active primary contact per Vendor and deactivate-not-destroy application lifecycle.
- Adds explicit Active/Inactive, reversible Archive, and reversible 30-day Trash lifecycle for Sourcing Vendors. Trash requires exact Vendor-code confirmation and a reason; no application hard-delete action is exposed.
- Records immutable `AuditArea.SOURCING` evidence for Vendor master, lifecycle and contact-person mutations and exposes a bounded Vendor Activity timeline.
- Enforces `sourcing.vendors.view` for every Vendor read surface and `sourcing.vendors.manage` for every mutation, including direct lifecycle/contact endpoints.
- Keeps the module reference-only: no Vendor action creates Inventory suppliers/stock, purchase/payable records, workers, Payroll activity or Accounting entries.
- Adds migration `sourcing.0002_vendor_directory_master`, focused Vendor-master regressions, `merge/sourcing-vendor-master.json`, `docs/SOURCING_VENDOR_MASTER.md`, and a mandatory release gate.
- Binds this release to exact 1.0.100 predecessor SHA-256 `4fba174a74f472ef419b62a05082ceb12625a439d925c6006e3f1582d388db88`.

# 1.0.100 — Sourcing Access-Control Authority

- Enables the independent **Sourcing Directory** only through explicit persisted Access Profile permissions; no Inventory, Payroll, Rental Manpower, Finance, Storekeeper, Foreman or other operational role inherits Sourcing access.
- Adds seven permissions: Vendor Sourcing view/edit, Manpower Sourcing view/edit, Sourcing Reference Masters view/edit, and Sourcing export. Edit grants require their matching view permission; export requires at least one Sourcing view grant.
- Company Owner is the only built-in profile that receives the new Sourcing permissions automatically. Existing Access Administrators can create custom profiles such as Vendor Viewer, Vendor Editor, Manpower Viewer, Manpower Editor or mixed Sourcing roles and assign them when creating/editing users.
- Adds `accounts.0012_sourcing_access_control_authority`, extending the database permission check constraint from 87 to 94 allowed permission keys and reconciling existing built-in Owner profiles without widening any other built-in role.
- Adds permission-aware Sourcing module visibility to the shared module switcher and `/app/sourcing/` backend enforcement. Direct access without a `sourcing.*` grant returns HTTP 403.
- Keeps the 1.0.99 reference-only isolation contract unchanged.
- Binds this release to exact 1.0.99 predecessor SHA-256 `3de0aa62e4045695764b4deb6378d8ea32b708afdd541612b8c2a7fb5e906326`.

# 1.0.99 — Sourcing Domain Foundation

- Adds a completely separate **Sourcing Directory** Django domain for reference-only Vendor and Manpower sourcing. It does not reuse Inventory suppliers or Rental Manpower suppliers.
- Adds company-scoped `SourcingVendor`, `SourcingMaterial`, Vendor supply offers, `SourcingManpowerSupplier`, `SourcingTrade`, Workforce offers and per-company freshness settings.
- Adds immutable Vendor-offer and Workforce-offer verification revision tables so future quantity/rate refreshes can preserve before/after history rather than overwrite evidence.
- Makes quantity and rate nullable and supports explicit Unknown availability so sourcing data is never misrepresented as live stock or committed workforce.
- Adds `AuditArea.SOURCING` plus a Django system check that rejects any Sourcing database relation into Inventory, Projects, Internal Payroll, Rental Manpower, Documents or Data Exchange.
- Registers `/app/sourcing/` and `PlatformModule.SOURCING`, but intentionally keeps the module fail-closed for every normal membership until Upgrade 1.0.100 introduces explicit Vendor/Manpower view/edit permissions.
- Adds migrations `core.0006_sourcing_audit_area` and `sourcing.0001_sourcing_domain_foundation`, focused domain-isolation regressions, operator documentation and a mandatory release gate.
- No Payroll formula, Rental settlement formula, Inventory quantity formula or existing operational lifecycle behavior changes.
- Binds this release to exact predecessor 1.0.98 SHA-256 `ee87fc1253b800e1f4a336cae00283160d3379b3d73f1b6efd6678014cf56e38`.

# 1.0.98 — Access History & Guarded Recovery

- Exposes the existing immutable Access audit ledger inside Administration through a bounded, server-paged **Access History** register guarded by the exact `access.audit.view` permission.
- Adds per-user Access History in the User drawer without granting edit authority to audit-only profiles.
- Adds guarded **Restore prior access** for authorized administrators. Recovery requires both `access.audit.view` and `access.users.manage`, exact username confirmation, and can only reapply the `before` snapshot from a supported immutable user-access event.
- Revalidates the historical Access Profile, Project scope, Branch/Office scope, Inventory Location scope, current lifecycle state, company boundary and final-owner protections before applying recovery.
- Recovery never rolls back usernames, email addresses, names or credentials from audit JSON. Successful recovery increments the target user's `security_version`, revokes existing sessions and appends a new immutable `access.user.access_restored` event referencing the source event.
- Uses page-size-plus-one pagination (25/50/100 rows) for Access History and avoids loading or counting the complete ledger during normal browsing.
- Adds focused Access History/recovery regressions, `merge/access-history-recovery.json`, `docs/ACCESS_HISTORY_RECOVERY.md`, and a mandatory production release gate. No database migration, Payroll formula, Rental settlement formula, Inventory quantity formula or lifecycle-retention semantic change.
- Binds this release to exact predecessor 1.0.97 SHA-256 `801d25b6f65a898f7f0dc96044df1e868949ff84db8547aff1ccc42788453ca4`.

# 1.0.97 — Credential & Session Revocation Hardening

- Adds `accounts.User.security_version` as a monotonic server-side session revocation stamp. Existing sessions become invalid on the next request after security-sensitive access changes.
- Revokes affected sessions after Access Profile assignment, Project/Branch/Inventory Location scope changes, membership activation/deactivation, temporary-password reset, legacy role changes and Django-superuser membership corrections.
- Editing the permissions or active state of a custom Access Profile revokes sessions for every assigned identity, preventing an already-open browser shell from continuing under stale authorization.
- Enforces `must_change_password`: temporary-password users are redirected to the dedicated password-change screen and operational APIs fail with HTTP 428 until the password is replaced.
- A successful personal password change clears the mandatory flag, rotates Django's authentication hash, increments/stamps the new security version and records an immutable Access audit event. Stale API sessions fail with explicit HTTP 401 `session_revoked`.
- Adds migration `accounts.0011_user_security_version`, focused session-security regressions, `merge/credential-session-revocation-hardening.json`, operator guide `docs/CREDENTIAL_SESSION_REVOCATION.md`, and a mandatory release gate.
- No Payroll calculation formula, Rental settlement formula, Inventory quantity formula, document snapshot, or lifecycle-retention semantic change.
- Binds this release to exact predecessor 1.0.96 SHA-256 `a94d4a289abac628d6305db7def2c41e4255ae6def8bab1dad89f13f667b4751`.

# 1.0.96 — Cross-module Access Leak Closure

- Closes indirect authorization leaks across global search, employee profile deep links, finalized Documents, report/export surfaces, Management aggregates, Archive/Trash and server-backed selectors.
- Applies Branch scope to live Internal employee directories/profile access and immutable Branch snapshots to historical payroll/payment/report/document rows.
- Applies Project scope to Rental supplier lookup, settlements/payments, Documents, reports and recovery registers; narrowed supplier views no longer project company-wide financial metrics.
- Requires the underlying sensitive page permission in addition to generic Reports permission, so WPS, Payments, Payroll and Settlement reports cannot be inferred through Reports-only profiles.
- Fails company-wide Management overview/approval/audit surfaces closed when data scopes are narrowed, and prevents Access Administrators from receiving finance/workforce aggregates merely because they can open Administration.
- Makes global search require `shared.search.use` and query only entity endpoints backed by the caller's exact page permission.
- Adds focused runtime regressions and `merge/cross-module-access-leak-closure.json`; no database migration, Payroll formula, settlement formula or Inventory quantity formula changes.
- Binds this release to exact predecessor 1.0.95 SHA-256 `1591e72505ceb6b3c9720dc62c53568eaf00ed9f624be255cb270af3ddb45425`.

# 1.0.95 — Internal Payroll + Finance Permission Decomposition

- Separates Internal Payroll preparation from independent Finance Review, final approval, Bank/WPS export and payment execution instead of relying on broad edit/approve/pay capabilities.
- Adds the exact `internal.payroll_runs.review` permission and freezes built-in duty separation: Internal Payroll Officer prepares, Finance Reviewer reviews/returns, and Finance Manager final-approves and executes payments. Finance Manager does not inherit Finance Review authority; review and final approval are distinct actors from the submitter and from each other.
- Adds immutable finance-review sign-off evidence to PayrollRun (`reviewed_at` / `reviewed_by`). Final approval fails closed until a separate finance review has been recorded against the locked, source-valid payroll snapshot.
- Enforces action-specific permissions in Attendance, Adjustments, Payroll Run and Salary Payment APIs/services so a permission for one workflow action cannot be reused for another action sharing the same endpoint.
- Decouples Bank/WPS file generation from payment execution: authorized Payroll staff may prepare/export files without gaining payment-posting/reconciliation authority; payment execution remains Finance-only.
- Makes server workflow projections and the Payroll browser consume the exact prepare/review/approve/export/execute permissions, including a distinct **Mark Reviewed** step before **Final Approve**.
- Adds migrations `accounts.0010_internal_finance_permission_decomposition` and `internal_payroll.0014_payroll_review_signoff`, focused regressions, `merge/internal-finance-permission-decomposition.json`, and a mandatory production release gate.
- The curated production-E2E contract now covers 34 scenarios / 181 critical Django methods / 24 runtime labels. No Payroll calculation formula, Rental settlement formula, document snapshot or Inventory quantity formula changes.
- Binds this release to the exact 1.0.94 predecessor archive SHA-256 `9920b4009f29fdf1dd09db51bb5fdf5c29eb4ecc32c937961c5537e0fa20e6d3`.

# 1.0.94 — Page-level View Only + Custom Access Profiles

- Adds production CRUD for company-scoped **custom Access Profiles** over the existing 1.0.88 permission tables. Built-in profiles remain immutable, assigned profiles cannot be deleted, active assigned profiles cannot be disabled, and an administrator cannot alter the profile currently granting their own authority.
- Adds the Administration → **Access Profiles** workspace with grouped page/action permissions and a View-only mode. Custom profiles can expose narrow combinations such as Internal Employees + Attendance or Rental Workers + Timesheets without granting edit authority.
- Enforces permission coherence when saving custom profiles: action permissions require the corresponding page-view permission, preventing invisible edit-only profiles. Profile create/update/delete changes are recorded on the immutable Access audit ledger.
- Moves Internal Payroll read/write endpoints from broad workspace authority to exact method-level page/action permissions across Employees, Organization, Attendance, Salary Setup, Payroll Runs, Adjustments, Salary Payments and WPS. A view permission never authorizes POST/PATCH/DELETE.
- Makes Internal Payroll browser navigation exact-permission aware and falls back to the first authorized page instead of assuming Overview exists. Unauthorized deep links fail closed in the browser while the backend independently rejects the API request.
- Makes the initial Payroll HTML bootstrap page-aware: an Employee-only viewer no longer receives Attendance roster/records/overtime merely because both pages belong to the Internal workspace. Rental and Inventory continue to retain their 1.0.92/1.0.93 scoped backend authorities.
- Adds focused custom-profile/view-only regressions, `merge/page-level-view-only.json` and a mandatory production release gate. The curated E2E contract now covers 33 scenarios / 172 critical Django methods / 23 runtime labels.
- No database migration, Payroll formula, Rental settlement formula, document snapshot or Inventory quantity change.
- Binds this release to the exact 1.0.93 predecessor archive SHA-256 `a202be1a77f796734822d4356abc3a681c7850cc3e3a74ac4f9aab1cfc94e2cb`.

# 1.0.93 — Inventory Storekeeper Scoped Authority

- Freezes the built-in **Storekeeper** Access Profile to exactly eleven operational permissions: Inventory overview/stock/movement/project/supplier/location visibility, receive, issue, transfer, scoped export and shared search. It does not inherit adjustment, reversal, import, master-management, Archive or Trash authority.
- Enforces Inventory access as the intersection of **Project scope + Inventory Location scope**. Project-backed locations must satisfy both boundaries; office locations require the Inventory Location grant, and `all`, `selected` and `none` modes remain backend-authoritative.
- Applies scope to stock, movements, projects, locations, low-stock counters, dashboard totals, direct detail routes and filtered exports. Direct URLs cannot bypass the same selectors used by normal navigation.
- Requires both source and destination locations to be in scope before a Storekeeper can transfer stock. Receive/Add and Issue/Use are separately protected by exact permissions and server-side scope revalidation.
- Keeps stock adjustment, movement/transfer reversal, Excel imports, Project/Supplier/Location administration and Archive/Trash lifecycle outside the Storekeeper profile. Read-only supplier/location/project surfaces remain available only where the profile grants their view permission.
- Makes Inventory navigation and action controls consume the server-issued effective permission snapshot, so Storekeepers do not receive manager-only controls while backend services remain the final authority.
- Adds `accounts.0009_storekeeper_scoped_authority`, which reconciles existing system Storekeeper profiles to the exact operational grant set without changing any user's existing Project/Location scope selections.
- Adds Storekeeper scope regressions, `merge/inventory-storekeeper-scope.json` and a mandatory release gate. No Inventory quantity formula, Payroll formula, settlement calculation or document snapshot change.
- Binds this release to the exact 1.0.92 predecessor archive SHA-256 `ec1388afc1833098292fc59fd9b93b3d92734f4be4e087584690943d39be2763`.

# 1.0.92 — Rental Supervisor / Foreman Scoped Access

- Adds a built-in **Rental Supervisor / Foreman** Access Profile with exactly nine operational permissions: scoped Rental overview, worker/assignment visibility, timesheet view/edit/submit and overtime view/edit/submit. It does not inherit supplier, settlement, payment, approval, lifecycle, document, report, archive or trash authority.
- Enforces Project scope on Rental project, worker, assignment and timesheet selectors/services/APIs. `all`, `selected` and `none` scope modes fail closed consistently, and selected supervisors cannot enumerate the supplier-wide unassigned worker pool.
- Allows Foremen to enter attendance/timesheet values and overtime for assigned projects and **Submit for Review**, while approval, locking and return-to-draft remain separate `rental.timesheets.approve` authority. The `submit_for_review` alias now resolves to the submit permission at the API boundary.
- Removes direct-data bypasses around scoped UI: Supplier, settlement/payment, adjustment/lifecycle, document finalization/report and Archive/Delete recovery endpoints require their exact granular permissions rather than broad Rental workspace access.
- Suppresses assignment and overtime commercial rates from Foreman worker, assignment-activity, timesheet-roster and overtime payloads; Foremen can enter operational OT hours but cannot view or override the commercial OT rate. Hourly assignment OT rates are derived server-side, while Daily/Monthly OT requires a manager-configured rate before supervisor entry. Financial settlement metrics and supplier directories are not built for the Foreman bootstrap.
- Prunes Rental navigation, Quick Add, notification content and overview data fetches from the server-issued permission snapshot. The scoped Supervisor overview never loads the settlement/payables context.
- Adds `accounts.0008_rental_supervisor_profile`, which extends the membership classification constraint and creates one exact system Foreman profile per existing company without changing any existing user's access assignment.
- Adds focused Project-scope/permission regressions, `merge/rental-supervisor-scope.json`, and a mandatory release gate. No Payroll formula, supplier-settlement formula, document snapshot or Inventory quantity logic changes.
- Binds this release to the exact 1.0.91 predecessor archive SHA-256 `8d565a1567ad41c50c8a27815b0ee67bffdf56f6ccc2ae11c0473fbf1a3e3cdb`.

# 1.0.91 — Administration / Users UI

- Adds **Administration** as a third authorized SESCCO MS module beside Inventory Management and Payroll Management. The module appears only when the active Access Profile has `access.users.view`; direct `/app/administration/` access is protected by the same backend permission.
- Adds the production **Administration → Users** workspace over the 1.0.90 company-scoped User Management APIs, without introducing a second authorization path or browser-side role authority.
- Adds a bounded 25/50/100-row Users register with two-character server search, Active/Inactive filtering, page-size-plus-one navigation, stale-request cancellation, and no full company user hydration.
- Adds Add/View/Edit User drawers with company identity fields, Access Profile assignment, effective profile summaries, and explicit Project / Branch & Office / Inventory Location scope controls using bounded server-backed lookup.
- Adds administrator security flows for temporary password reset, activate/deactivate and guarded unused-account deletion. Self-access changes and non-owner modifications of Owner accounts remain blocked by the backend and are reflected as disabled UI actions.
- Keeps temporary passwords transient: creation/reset fields never persist to browser storage, and the backend continues to store only the Django password hash while setting `must_change_password`.
- Keeps Django administration separate from SESCCO application administration; Access Administrators remain non-staff application users.
- Adds responsive Administration shell styling, module-switcher integration, focused Django regressions, `merge/user-management-ui.json`, and a mandatory static release gate.
- Carries the 1.0.90 backend authority, 1.0.89 profile-only runtime authorization and all Payroll/Inventory scale/lifecycle contracts forward unchanged. No database migration, Payroll formula, settlement, document snapshot or Inventory quantity change.
- Binds this release to the exact 1.0.90 predecessor archive SHA-256 `e583e7ce5d459171665463906a6672bc05e2bf1870e07357d1fa28f274980289`.

# 1.0.90 — User Management backend CRUD

- Adds production company-scoped User Management APIs for bounded user search/listing, user creation, identity/profile/scope updates, activation/deactivation, guarded unused-account deletion and administrator password reset.
- Keeps `CompanyMembership + AccessProfile + EffectiveAccess` as the only application authorization authority; the new `custom` membership classification is metadata for administrator-defined profiles and never grants permissions by itself.
- Adds forced-change credential state (`must_change_password`, `credentials_updated_at`). New users and administrator password resets set a temporary password through Django password validation and invalidate existing sessions through the changed authentication hash; password values are never written to audit payloads.
- Enforces owner and administrator safety at the service boundary: non-owners cannot assign/modify/reset Owner accounts, administrators cannot change their own access profile/scopes or deactivate themselves, and the existing final-owner protection remains authoritative.
- Adds atomic Project, Branch/Office and Inventory Location scope replacement with same-company validation and explicit All / Selected / None semantics; Selected requires at least one valid scope record.
- Adds active Access Profile discovery plus bounded 25-row scope lookup for the upcoming Administration UI. User directories use 25/50/100-row server pages and two-character server search rather than hydrating all company users or scope masters.
- Hard deletion is limited to never-signed-in, single-company identities with no actor audit history and exact username confirmation; established identities must be deactivated so historical attribution remains intact.
- Extends immutable Access audit coverage with create/update/activate/deactivate/password-reset/delete-unused events and adds focused backend/API regressions plus a mandatory release gate.
- Adds migration `accounts.0007_user_management_backend`; no Payroll formula, settlement calculation, document snapshot, Inventory quantity or lifecycle-retention behavior changes.
- Binds this release to the exact 1.0.89 predecessor archive SHA-256 `9ada5322a3a2768534356d50b184c62f6a003b7b1ff2b2b34f86c64b174908bd`.

# 1.0.89 — Single authorization authority cutover

- Retires `accounts.User.role` and the old Inventory `is_inventory_admin` compatibility authority. SESCCO application authorization now lives only on `CompanyMembership` + `AccessProfile` + request-cached `EffectiveAccess`.
- Makes `CompanyMembership.access_profile` required. Migration `accounts.0006_single_access_authority` fills any residual profile gaps from frozen system-profile templates before applying the NOT NULL boundary, then removes `User.role`.
- Rewrites legacy workspace/edit/capability compatibility helpers to derive exclusively from granular Access Profile permissions. No request path can gain Inventory, Internal Payroll, Rental Manpower, approval, payment, settings or access-management authority from `CompanyMembership.role`.
- Keeps `CompanyMembership.role` temporarily as non-authoritative classification/provisioning metadata so existing records and the pre-Administration UI remain readable; changing the label alone cannot expand a member’s effective permissions.
- Moves last-owner protection from the role string to the active system owner Access Profile (`role-owner`) for user deactivation, membership deactivation and system-profile changes.
- Separates Django administration from SESCCO administration: non-superusers are forced out of `is_staff`, and `merge_access_report --fail-on-errors` now rejects any non-superuser Django staff account.
- Updates Payroll browser authorization controls so workspace visibility, edit state, approval, payment, settings and access visibility consume the server’s profile-derived workspace/capability snapshot instead of the role matrix.
- Adds production reconciliation, regressions, `merge/single-access-authority.json` and a mandatory single-authority release gate. No Payroll formula, settlement calculation, document snapshot or Inventory quantity logic changes.
- Binds this release to the exact 1.0.88 predecessor archive SHA-256 `9e4df9abef2a0417fd6f79f6cfbb70b333ee99b235fc2ec6e76efc420baaf565`.

# 1.0.88 — Granular access authority foundation

- Adds company-scoped `AccessProfile` and `AccessProfilePermission` authority with an explicit 86-key permission catalog covering Administration, Inventory, Internal Payroll, Rental Manpower and shared document/report/lifecycle surfaces.
- Adds an **Access Administrator** compatibility role for user/access administration without automatic Inventory or Payroll operational authority.
- Adds explicit membership scope modes (`all`, `selected`, `none`) plus normalized Project, Branch/Office and Inventory Location scope tables; every scope record validates the same company boundary as its membership.
- Backfills every existing company with system access profiles derived from the current role matrix and assigns every existing membership to its equivalent profile with all three scopes defaulting to `all`, preserving current production access during migration.
- Adds a request-level `EffectiveAccess` snapshot and membership-instance permission cache. Frontend bootstrap receives permission keys and scope modes only; large project/branch/location master lists are not injected into the shell.
- Adds granular page/API permission decorators and reusable scope guards/queryset restrictors for the later User Management, Foreman and Storekeeper cutovers while leaving existing workspace/capability enforcement intact in this compatibility release.
- Keeps membership creation and legacy role-change services synchronized with their system Access Profile and extends `merge_access_report --fail-on-errors` to reject missing profiles, cross-company profile assignments, missing system profiles and permission drift.
- Adds `accounts.0005_granular_access_authority`, focused regressions, `merge/granular-access-authority.json` and a mandatory production release gate. No Payroll formula, settlement calculation, document snapshot or Inventory quantity logic changes.
- Binds this release to the exact 1.0.87 predecessor archive SHA-256 `e6f162cf550d92101ed761831c582e501a801c9116d0a156e40433182a09f1d6`.

# 1.0.87 — Contextual document finalization hotfix

- Fixes Internal Employee → Documents → Finalize Salary Slip so the drawer preserves the selected employee and working period instead of falling back to the company-wide document-source search.
- Locks employee-profile finalization to Salary Slip, shows the selected employee and period as read-only context, loads only that employee’s Approved-or-later unfinalized payroll line, and automatically selects the single eligible source.
- Adds backend `employee_id` scoping to bounded Salary Slip and Salary Payment Receipt source lookup while preserving company authorization, 25-row request caps, page-size-plus-one paging and already-finalized exclusion.
- Removes Supplier Invoice controls from unrelated document drawers entirely: invoice number, issue date and VAT fields are created only when `supplier_invoice` is the selected document type.
- Adds a defensive CSS hidden-section guard so future type-specific form sections cannot be forced visible by the shared `.form-section { display: grid; }` rule.
- Keeps the user on the Internal Employee Documents tab after finalizing a salary slip, with the new immutable document immediately visible in that employee’s history.
- Adds Django regressions and a mandatory release gate for employee-scoped source selection and document-type-only fields. No database migration, Payroll formula, settlement formula or immutable document snapshot semantics change.
- Binds this hotfix to the exact 1.0.86 predecessor archive SHA-256 `e524860b5f7d47582f8676a74d40d929c97b87cff36afc17bff2d4ed36101256`.

# 1.0.86 — Cross-workspace drawer selector scale hardening

- Audits Internal Company and Rental Manpower editing drawers for high-cardinality master/transaction selectors and applies one consistent search-inside-dropdown safety pattern.
- Internal Company: Add Employee Branch/Department, Change Organization Branch/Department, and Salary Structure Employee selection now use bounded server-backed lookup instead of full browser master lists.
- Rental Manpower: Add Worker Supplier, Worker Advance Project, and Supplier Payment Approved Settlement selection now use bounded server-backed lookup instead of full browser master/financial lists.
- Shared Documents: Finalize Document now uses one search-inside-dropdown Source selector in both Internal and Rental workspaces; the previous separate Find Source + Source select controls are removed.
- Growing master searches require at least two characters; document sources can browse bounded pages where safe and require two characters for employee/payment source types. All searchable dropdowns render 10 results per in-menu page, hard-cap requests at 25 rows, use page-size-plus-one rather than an exact COUNT query, and abort stale requests.
- Supplier Payment lookup exposes only approved/payment-processing/partially-paid settlements with a remaining payable balance; paid and in-flight allocations are calculated server-side before a settlement can be selected.
- Save actions post selected UUIDs directly and retain backend company/lifecycle/financial validation as final authority; large browser caches are no longer required to submit these drawers.
- Keeps genuinely bounded configuration selectors such as status, transaction type, rate type, payment method and overtime policy as normal dropdowns.
- Corrects an unrelated Assignment Project lookup initializer that had been attached to the Bank Template drawer instead of the Rental Assignment drawer.
- Adds bounded lookup regressions and a mandatory release gate covering both workspaces. No database migration, Payroll formula, settlement formula, lifecycle-retention or document-output change.
- Binds this release to the exact 1.0.85 predecessor archive SHA-256 `6154d3211c34c153ffbe91f45dde8fb817b4597a10d021d422a6ce38cdcd7f2b`.

# 1.0.85 — Assignment project searchable-dropdown scale safety

- Replaces the Assignment Lifecycle **Transfer to project** and **Assign to project** full project `<select>` controls with the same clean search-inside-dropdown interaction used by the hardened adjustment selectors.
- Project search is server-backed, requires at least two characters, returns 10-row dropdown pages, and is hard-capped at 25 rows per request. The lookup uses page-size-plus-one detection instead of an exact COUNT query.
- Filters lookup results to company-scoped Active projects whose project lifecycle dates allow the selected assignment effective date. Transfer search also excludes the worker's current project.
- Changing the effective date clears any selected target project and requires a fresh date-valid lookup; stale project-search requests are aborted.
- Removes the save-time dependency on the browser `state.projects` cache. The selected project UUID is posted directly and `assign_worker` / `transfer_worker` remain the transactional authority for project lifecycle, worker lifecycle, same-project transfer rejection, overlap and timesheet-snapshot safety.
- Adds Django regressions and a mandatory static release gate for bounded assignment-project lookup.
- No database migration, Payroll formula, settlement calculation, permission, lifecycle-retention or document-output change.
- Binds this release to the exact 1.0.84 predecessor archive SHA-256 `8c324c4011874d20d71aea0d0e7029a0a750edc06824d834cda5fed35fb2b41a`.

# 1.0.84 — Adjustment drawer clean alignment hotfix

- Removes persistent feature-explanation helper text beneath the Adjustment Person and Project searchable dropdowns so the two-column Transaction owner controls align cleanly.
- Removes the selected Project supplier/trade/effective-date metadata line from below the Project field; that metadata remains available inside the Project dropdown result rows.
- Keeps search instructions, loading/empty states, pagination and validation inside the opened dropdown instead of consuming permanent drawer layout space.
- Preserves the 1.0.83 server-backed selector safety contract: two-character person search gate, 10-row in-dropdown pages, 25-result request cap, stale-request cancellation, effective-assignment project restriction and transactional server revalidation on save.
- Carries all 1.0.82 production Payroll document/headpad hardening and the 1.0.81 Worker Adjustments bounded-page cutover forward unchanged.
- No database migration, Payroll formula, lifecycle, permission, document snapshot or financial-calculation change.

# 1.0.83 — Adjustment searchable-dropdown UX & scale hardening

- Replaces the separate Find worker / Person and Find project / Project controls in the Rental Worker Adjustment drawer with one clean searchable dropdown per field. Search lives inside the opened dropdown instead of consuming permanent drawer space.
- Keeps Person search server-backed and two-character gated. Results are requested in 10-row dropdown pages and the API remains hard-capped at 25 rows per request; no worker master is hydrated into the browser.
- Adds Previous/Next controls inside the dropdown only when another lookup page exists. The lookup uses page-size-plus-one detection rather than an expensive exact-count query.
- Keeps Project disabled until a worker is selected, then exposes only active projects from that worker's effective assignment on the transaction date. Exact selected-project revalidation is supported when the effective date changes.
- Preserves stale-request cancellation independently for Person and Project searches, closes the dropdown on selection/outside click/Escape, and keeps required-field validation on the custom controls.
- Applies the same compact searchable Person selector pattern to Internal Company adjustments for visual consistency while preserving the existing bounded Internal employee API.
- Adds a Django regression for paged worker lookup and strengthens the selector-scale release gate so external duplicate search fields or unbounded selector APIs cannot return.
- No schema migration, Payroll formula change, settlement calculation change, or relaxation of server-side worker/project/date authority.
- Binds this release to the exact 1.0.82 predecessor archive SHA-256 `24dcbdb2c440449b4b7f1352f3da955e468e3c908cade129d320f4994d473bc3`.

# 1.0.82 — Payroll document production hardening & SESCCO supplier headpad

- Uses the approved SESCCO A4 company headpad supplied in `Electronic PAD - PDF` as a versioned, hash-verified packaged letterhead for every newly finalized Supplier Invoice. The full-page artwork is rendered at 2480×3508 and snapshotted by SHA-256 so historical invoices cannot silently switch branding.
- Keeps Supplier Invoice letterhead independent from general company-branding settings: the official headpad is forced for this document type and its embedded watermark is not double-rendered.
- Hardens print/PDF layout for all seven immutable Payroll document types with A4 page contracts, repeated table headers, row/signature break protection, long-table page safety, explicit overtime sections, payment evidence, totals, and amount-in-words where financially relevant.
- Upgrades Supplier Invoice output with invoice/settlement/document identity, supplier CR/VAT/address, project/service period, worker-level regular/overtime hours, subtotal, VAT rate/amount, grand total, payment terms, amount in words and authorized-signature space.
- Upgrades Internal and Rental payment receipts with payment date/reference/method/evidence and amount in words; Internal and Rental timesheet prints now include their overtime snapshots instead of omitting them.
- Replaces the unbounded Finalize Document source dropdown with a type-first, server-backed source search capped at 25 eligible records. Salary-slip and salary-payment receipt lookup requires a two-character search, stale requests are aborted, and already-finalized sources are excluded in PostgreSQL.
- Adds a dedicated Payroll document production release gate, packaged-headpad integrity tests, and supplier-invoice branding regression evidence. No schema migration and no Payroll calculation formula change.
- Binds this release to the exact 1.0.81 predecessor archive SHA-256 `2dbef2c67179bdaceb4e99f87dc403cb05a28f26032d296618faca9a0b833b57`.

# 1.0.81 — Worker Adjustments page scale cutover

- Replaces the Rental Worker Adjustments page dependency on the full Rental Settlement context with a dedicated 25/50/100-row server-paginated register.
- Computes exact period transaction count, Approved earnings/deductions and awaiting-approval KPIs with database aggregates instead of hydrating every adjustment in browser memory.
- Moves Worker Adjustments search, type/status, Project and Supplier filtering to server authority; Project/Supplier filters are searchable text inputs rather than full-master `<option>` lists.
- Adds stale-request cancellation and bounded page state for rapid Worker Adjustments search/filter/page changes.
- Changes Rental adjustment create/update/workflow responses to compact single-adjustment deltas instead of returning settlements, payments, timesheet scopes and project workflows.
- Invalidates cached Rental Settlement authority after an adjustment mutation without reloading that heavy context just to refresh Worker Adjustments.
- Extends the 2,000 Internal / 5,000 Rental browser certification matrix with Rental Worker Adjustments as an explicit 24th high-cardinality surface, including server report and live Chromium coverage.
- Adds dedicated static and Django regression evidence. No schema or Payroll formula change.
- Binds this release to the exact 1.0.80 predecessor archive SHA-256 `64f297d9af26ffb4dc56f700c5195a40ec3afd397656f4fcb420d2f26e0d61dd`.

# 1.0.80 — Rental adjustment selector scale safety

- Replaces Rental Worker and Project master dropdown hydration in the Worker Adjustments drawer with bounded server-backed lookup.
- Worker search requires at least two characters and returns at most 25 company-scoped workers that have an effective assignment on the selected transaction date.
- Project search requires a selected worker and returns at most 25 active projects from that worker's effective assignment on the selected date; it cannot enumerate the global project master.
- Changing the effective date revalidates the selected worker and project, stale worker/project requests are aborted, and invalid selections are cleared before submission.
- Removes the complete Rental Worker master hydration previously triggered by the Rental Adjustments page solely for transaction ownership.
- Removes save-time dependence on browser worker/project caches; `create_rental_adjustment` remains the transactional authority for company scope, lifecycle, active project and effective assignment validation.
- Adds dedicated selector-scale static verification and three Django regression tests. No schema or Payroll formula change.
- Binds this release to the exact 1.0.79 predecessor archive SHA-256 `b51d771d99faab346f6970728821ccbcfd25842e930e14ff5e4e71a261b7d3a9`.

# 1.0.79 — Payroll frontend freeze-manifest hotfix

- Fixes the deployment failure in `scripts/verify-payroll-frontend.sh` where `merge/payroll-frontend-assets.sha256` still contained the pre-1.0.78 hash for `static/payroll/js/app.js`.
- Freezes the actual 1.0.78/1.0.79 Payroll JavaScript bundle hash so the merged-frontend deployment guard validates the exact shipped asset instead of rejecting it.
- Adds the merged Payroll frontend verifier to the top-level production-freeze chain, preventing a future release from passing the broad source freeze while carrying a stale narrow frontend manifest.
- Carries forward the 1.0.78 WPS Reports performance hotfix unchanged; there is no Payroll formula, schema, lifecycle, or application behavior change in this release.
- Binds this hotfix to the exact 1.0.78 predecessor archive SHA-256 `4f05fda6d0bac3235fd46bfbd7ae5e66809a20ab6dd1a86af6d95a521821a98d`.

# 1.0.78 — Reports/WPS performance hotfix

- Fixes the Reports page freeze/long refresh observed with the 2,020-profile WPS report even though the visible table was already server-paginated.
- The interactive WPS report now projects only the display fields needed by the current 25/50/100-row page. It no longer hydrates `EmployeePaymentProfile` instances or decrypts encrypted IBAN/salary-card destination fields that are not displayed.
- WPS profile, WPS-enabled and configured KPIs are computed in one database aggregate; the unfiltered page reuses that profile count instead of issuing another count query.
- Report period choices are fetched on the first report request and reused by the browser, avoiding repeated PayrollRun/SupplierSettlement period queries during search and pagination.
- Search, report-type, period, page and page-size interactions now refresh the report viewer in place instead of rebuilding the entire Payroll shell. The existing report stays visible while the replacement page is loading, stale requests are aborted, and search focus/cursor are restored.
- Removes misleading page-local client sorting from server-paginated report tables.
- Extends the deployment benchmark and live Chromium certification to explicitly exercise the WPS Report page and WPS Report search at the 2,000-employee benchmark scale.
- Adds a Django regression that fails if the interactive WPS report attempts to decrypt payment-destination secrets.
- No schema change and no Payroll formula change.

# 1.0.77 — Full 2K/5K Payroll browser certification & final production freeze

- Expands the final browser-scale contract across all 23 high-cardinality Payroll surfaces completed through 1.0.71–1.0.76, covering Internal directories/timesheets, Salary Setup, Payroll Runs/Review, Advances & Adjustments, Salary Payments, Bank/WPS, Documents, Reports, Archive/Delete, Management Approval/Audit, Rental workforce/timesheets/assignments, and global search.
- Extends `payroll_browser_scale_report` with server-side query/payload/row-budget measurements for the newly bounded Internal and shared Payroll selectors while retaining the 2,000 Internal employee / 5,000 Rental worker benchmark-volume requirement.
- Expands the live Chromium certification runner to exercise rapid search, filter, page, and workspace/tab changes across the final high-cardinality matrix instead of certifying only the original directory/timesheet/assignment surfaces.
- Freezes 25/50/100-row page sizes, a 100-row rendered business-table maximum, a 200-row expanded assignment-activity maximum, a 30-result global-search maximum, a 2.5 MB context payload ceiling, and stale-request authority requirements.
- Adds `merge/payroll-final-browser-certification.json`, `scripts/verify-payroll-final-browser-certification.py`, and curated runtime evidence so the expanded benchmark is required by release tasks, production freeze, and the release-candidate contract.
- Introduces no schema migration, Payroll formula change, or lifecycle semantic change; this is a certification/freeze release bound to the exact 1.0.76 predecessor SHA-256 `0fc4417270e8b8555456b173c5611266b74d169b45819a595299f0e2a085f5be`.

# 1.0.76 — Remaining Payroll data/render hardening

- Defers the finalized Business Documents register from Payroll bootstrap and loads it through bounded 25/50/100-row server pages with server-side search, workspace/period/type filters, and exact type/count summaries. Immutable snapshot detail is loaded only when a document is opened.
- Moves interactive Payroll Reports to bounded 25/50/100-row server pages with server-side search while preserving the explicit CSV export path as the full-result authority.
- Defers Archive/Delete registers from the shell and loads only the requested Internal/Rental workspace + archive/trash bucket through bounded server pages.
- Replaces the live Management bootstrap with a compact summary and a five-item approval attention preview; Approval Center and Audit Trail now use separate 25/50/100-row server endpoints.
- Adds server-side Audit search/type filtering with company-boundary and VIEW_AUDIT enforcement, plus cancellation authority so stale searches/pages cannot overwrite newer results.
- Registers Documents, Reports, Approval Center and Audit Trail page-size settings as UI-only browser preferences and removes their dependence on full browser arrays.
- Adds `merge/payroll-shared-surfaces-scale.json`, `scripts/verify-payroll-shared-surfaces-scale.py`, and curated regression evidence covering all remaining bounded shared Payroll surfaces. No schema migration, Payroll formula change or lifecycle semantic change is introduced.

# 1.0.75 — Salary Payments + Bank/WPS scale cutover

- Replaces the Internal Salary Payments opening payload with a compact shell: company settings, export templates and batch headers only; employee payment profiles, readiness rows and batch rows are no longer hydrated company-wide.
- Adds 25/50/100-row server pagination for Bank CSV and WPS readiness registers with server-side employee/bank search, readiness filtering and exact server-authoritative ready/blocked/amount totals.
- Scans readiness in bounded 250-employee server chunks and serializes payment-profile detail only for the visible page.
- Adds lazy per-employee payment-profile loading so direct profile editing no longer depends on a complete payment-profile map in browser memory.
- Adds 25/50/100-row server pagination for salary-payment batch reconciliation rows with server-side employee/bank/reference search, status filtering and PostgreSQL exact status/amount summaries.
- Changes salary-payment prepare/workflow/import/retry mutations to compact batch/row deltas; page/shell authority is refreshed explicitly instead of returning the full payment context.
- Removes the remaining Employee Directory WPS filter dependency on `salary_payment_context`; WPS classification now calls readiness authority directly without loading all payment batches or profiles into a response context.
- Adds stale-request abort authority and UI-only page-size preferences for Bank readiness, WPS readiness and payment reconciliation. No schema migration or Payroll formula change is introduced.

# 1.0.74 — Advances & Adjustments scale cutover

- Removes Internal Advances & Adjustments from the legacy full Payroll-period context and complete Internal Employee master hydration.
- Adds bounded 25/50/100-row server pagination for the Internal transaction register with server-side employee/ID/reason/reference search and type/status filtering.
- Keeps period transaction count, Approved earnings, Approved deductions and pending-review count exact and server-authoritative regardless of the visible/search-filtered page.
- Moves Salary Advance outstanding balances to PostgreSQL aggregation and paginates open employee balances at 25/50/100 rows; recovery-plan and pending-transaction detail is fetched only for the visible balance page.
- Replaces the adjustment drawer's all-employee selector with a server-backed employee search capped at 25 matches.
- Changes Internal adjustment create/update/workflow responses to a single adjustment delta instead of returning the entire Payroll run, previous run, and period adjustment context.
- Moves employee-profile adjustment history to the selected employee + selected period profile response, so profile correctness no longer depends on a browser-wide adjustment cache.
- Adds cancellation/request authority for rapid adjustment search/filter/page changes plus a dedicated scale regression contract. No schema migration or Payroll formula change is introduced.

# 1.0.73 — Payroll Run scale cutover

- Moves Internal Payroll Register and Review tables to bounded 25/50/100-row server pages with server-side employee search, Branch / Office, Department and readiness filtering.
- Stops saved payroll runs from prefetching every `PayrollRunLine`, salary component, adjustment and previous-period line just to open one page; detail prefetch now happens only after the visible page is sliced.
- Keeps exact period-level employee, gross, deduction and net totals server-authoritative and independent of the visible/search-filtered page.
- Limits previous-period variance payloads to the employees on the visible current page while retaining global previous/current run totals for the comparison cards.
- Adds global review exception counts so approval remains protected by all critical exceptions even though the employee review register is paginated.
- Adds cancellation authority for rapid Payroll Run search/filter/page changes and keeps the browser bounded to the requested page instead of growing a complete run cache.
- Keeps the legacy full Payroll period context isolated for Advances & Adjustments until the dedicated 1.0.74 cutover; bounded Payroll Run payloads do not mark that legacy context as loaded.
- Adds `merge/payroll-run-scale.json`, `scripts/verify-payroll-run-scale.py`, and Django regression coverage for saved-run pagination/search. No schema migration or Payroll formula change is introduced.

# 1.0.72 — Salary Setup scale cutover

- Replaces Salary Setup's complete Internal Employee master hydration with an employee-first server directory that paginates at 25/50/100 rows (50 by default).
- Stops `/api/internal/salary/structures/` from serializing every employee's complete effective-dated history when the workspace opens; only the visible page receives current structure lines.
- Adds server-side employee/ID/position search and Configured / Needs setup filtering for Employee Structures, with cancellation authority so stale searches cannot overwrite newer results.
- Adds exact server-authoritative salary coverage totals (`employeeCount`, `configuredCount`, `needsSetupCount`) independent of the visible page/search result.
- Moves effective-dated salary history to lazy per-employee loading through `?employee=<uuid>` and reuses that path for employee profile salary views and effective-change drawers.
- Replaces Assign Structure's browser-cache employee selector dependency with a server-backed employee search capped at 25 matches.
- Adds `merge/payroll-salary-setup-scale.json`, `scripts/verify-payroll-salary-setup-scale.py`, and Django regression coverage proving bounded structure pages and employee-scoped history.
- Preserves all 1.0.71 Internal Employee residual-scale guarantees and the 1.0.70 2,000 Internal / 5,000 Rental benchmark boundary. No schema migration or Payroll formula change is introduced.

# 1.0.71 — Internal Employee residual performance cutover

- Removes the hidden all-company salary-payment/WPS context build from ordinary paged Internal Employee directory requests. Employee rows are paginated first and only the visible page receives salary/payment readiness enrichment.
- Adds a server-authoritative Internal Employee summary endpoint for exact workforce, active, salary-configured, WPS-profile, attendance-entry, branch and department counts without hydrating the complete employee master in the browser.
- Caps the normal browser-side Internal Employee directory cache at 250 records while preserving the 25/50/100 visible page-size contract and direct-profile deep links.
- Replaces Branch / Office and Department profile full-master hydration with a bounded 50-row workforce preview plus exact server aggregates and server-derived organization distributions.
- Keeps explicit WPS Ready / Needs Setup filtering authoritative over the complete filtered population; that exceptional full-context path is intentionally isolated for the dedicated Salary Payments + Bank/WPS cutover planned in 1.0.75.
- Adds focused regression coverage and `merge/payroll-employee-residual-scale.json` / `scripts/verify-payroll-employee-residual-scale.py` to prevent ordinary employee pagination or organization profiles from regressing to full-master work.
- Extends the curated Payroll production-E2E contract to 13 high-risk scenarios / 79 critical methods, including direct proof that an ordinary employee page never invokes the full salary-payment context and that scoped summaries return exact counts.
- Adds abort authority for employee summary and organization-profile requests after mutations, and prefetches Payroll snapshot components/adjustments so visible-page WPS readiness does not create per-row query fan-out.
- Preserves the 1.0.70 2,000 Internal / 5,000 Rental browser-scale guarantees. No schema migration or Payroll formula change is introduced.

# 1.0.70 — 5K/2K browser benchmark certification & production freeze

- Freezes the large-data runtime work introduced in 1.0.65–1.0.69: cancellation-aware directory search, Assignment Lifecycle server pagination, bounded Attendance/Timesheet pages, thin Payroll bootstrap, server-backed global search and PostgreSQL query/index hardening.
- Adds `merge/payroll-browser-scale.json` and `scripts/verify-payroll-browser-scale.py` to enforce the complete 2,000 Internal / 5,000 Rental browser-scale boundary from backend selectors through rendered page limits.
- Adds `payroll_browser_scale_report` for benchmark-database certification of 100-row Internal Attendance, Internal Employee search, Rental Worker search, Rental Assignment activity and Rental Project Timesheet payload/query bounds. The report can require the full 2,000/5,000 seed volume and fail on payload/query limits.
- Adds `scripts/certify-payroll-browser-scale.py`, a live Chromium/Playwright runner for rapid search, pagination and loading-state checks across Internal Attendance, Rental Assignment Lifecycle, Rental Project Timesheets and global search. It writes `payroll-browser-certification.json` evidence and does not hard-code portable sub-second timing assumptions; the default stuck-interaction ceiling is 10 seconds and can be overridden for the release environment.
- Extends the curated Payroll production-E2E suite with a browser-scale regression scenario, bringing the frozen certification contract to 12 high-risk scenarios and 77 critical test methods across 20 evidence files / 15 runtime labels.
- Carries the 1.0.69 PostgreSQL `pg_trgm` and concurrent index migrations forward unchanged. This release adds no schema migration, Payroll formula change, lifecycle semantic change or new user feature.
- Binds the final release to the exact 1.0.69 archive SHA-256 and requires both the static browser-scale gate and benchmark/live-browser evidence before calling the large-data performance work fully certified.

# 1.0.69 — PostgreSQL search & query hardening

- Replaces join-heavy Internal Employee, Internal Attendance and Rental Worker live-search filters with correlated `EXISTS` predicates so server pagination no longer depends on large assignment joins followed by `DISTINCT`.
- Reworks Rental Assignment Activity text search to use indexed worker/project subqueries plus assignment-local text predicates instead of broad joined text scans.
- Adds PostgreSQL `pg_trgm` GIN indexes for high-cardinality employee/worker identity fields and assignment trade/reason text used by live Payroll search.
- Adds partial current-organization/current-project lookup indexes for branch, department and Rental assignment scopes.
- Builds the new indexes with `AddIndexConcurrently` in non-atomic migrations so production search hardening does not require a long table-write lock.
- Adds `merge/payroll-query-hardening.json` and `scripts/verify-payroll-query-hardening.py`, and makes the query-hardening gate mandatory in production freeze and release tasks.
- Adds `payroll_search_query_report` for post-deploy query-count/timing checks and optional PostgreSQL `EXPLAIN` output against the benchmark database.
- This release changes indexes/query plans only; Payroll formulas, lifecycle semantics, permissions and benchmark seed data are unchanged.

# 1.0.68 — Thin Payroll bootstrap & server-backed global search

- Bounds the initial Payroll HTML bootstrap to 50 Internal employee masters and 50 Rental worker masters instead of serializing the complete 2,000/5,000 benchmark workforce into every page load.
- Removes Rental assignment history from the initial shell payload and defers complete workforce masters to the few legacy profile/transaction selectors that actually require them.
- Defers salary setup, Internal payroll-period data and salary-payment readiness until their routes are opened; Attendance remains on its existing bounded 50-row bootstrap.
- Replaces Ctrl/Cmd+K browser scans of all employees/workers with cancellation-aware server directory search across employees, branches, departments, workers, projects and suppliers, limited to five results per entity type after a 320 ms debounce.
- Adds direct backend hydration for employee and Rental worker deep links so profiles outside the initial 50-row bootstrap still open correctly.
- Merges only Payroll/WPS readiness identities returned by server contexts rather than loading the whole employee directory for financial screens.
- Keeps Adjustment person selectors correct by lazily hydrating the complete relevant master only when that transaction route is opened.
- Adds `merge/payroll-bootstrap-search.json` and `scripts/verify-payroll-bootstrap-search.py` and carries the thin-bootstrap/search gate into production freeze and release tasks.
- No database migration, Payroll formula, permission, lifecycle or benchmark-seed semantic change.

# 1.0.67 — Attendance & Timesheet scale cutover

- Moves Internal Attendance, Internal Overtime and Rental Project Timesheets to bounded 25/50/100-row server pages for the 2,000/5,000 benchmark dataset.
- Rental Timesheets now render only the backend project-period roster and no longer scan the complete 5,000-worker master or all assignment histories in the browser.
- Adds cancellation-aware 320 ms search/filter requests for Internal Attendance and Rental Timesheets so obsolete requests cannot queue behind the active query or overwrite newer results.
- Attendance and Rental Timesheet cell/OT mutations return compact deltas instead of resending the complete monthly roster and daily matrix.
- Adds server aggregate summaries for full-period employee/worker counts, regular hours, overtime and missing entries while table rendering remains bounded to the visible page.
- Bounds the initial Internal Attendance bootstrap to 50 rows; arbitrary attendance imports force only the current bounded page to refresh after commit.
- Keeps client CSV export intentionally bounded to the current filtered page and labels it accordingly; exact full filtered export remains a later server-export concern.
- Adds Django regression coverage and `merge/payroll-timesheet-scale.json` / `scripts/verify-payroll-timesheet-scale.py` to prevent full-roster payloads or browser-side scans from returning.
- No database migration, Payroll formula, permission or lifecycle semantic change.

# 1.0.66 — Rental Assignment Lifecycle server pagination

- Moves Assignment Activity, Current Deployment and Supplier Pool off the complete browser-side rental-worker/history scan and onto bounded backend views.
- Adds 25/50/100-row server pagination, server-side search/supplier/project/event filtering, request cancellation and stale-response protection for Assignment Lifecycle.
- Replaces route-level history/integrity scans with server summary counts and mutation-driven cache invalidation.
- Keeps existing assignment mutation semantics, audit history, Payroll formulas and database schema unchanged.

# 1.0.65 — Payroll directory search & loading hotfix

- Fixes the server-directory completion-order defect that rendered the active page before clearing `loading`, which could leave Rental Workforce and the other paged master directories permanently showing “Loading directory…” after the backend response had already completed.
- Adds one AbortController-owned request per server-backed Payroll directory. Fast search/filter changes now abort obsolete requests instead of allowing stale network work to accumulate behind the current query.
- Raises the six server-directory search inputs to a 320 ms cancellation-aware debounce: Branches / Offices, Departments, Internal Employees, Projects, Manpower Suppliers and Rental Workforce.
- Preserves the last valid page of rows while a replacement query is loading so search no longer blanks the table into a full-height loading state; Rental Workforce shows a small `Refreshing…` status while the bounded replacement page is in flight.
- Replaces per-row full-master `findIndex` scans with one ID→index map when merging paged directory results, and recalculates salary display data only for the returned employee page instead of all 2,000 benchmark employees after every search response.
- Adds a failed-request key so a backend error does not create an automatic render/retry loop. Explicit Retry remains available and clears that failure authority before requesting again.
- Keeps existing server pagination/page-size limits and stale-response request IDs intact. No Payroll formula, lifecycle, permission, database schema or benchmark seed behavior changes in this hotfix.
- Adds `merge/payroll-directory-runtime.json` and `scripts/verify-payroll-directory-runtime.py`, and wires the runtime-search contract into the packaged Payroll/frontend and production-freeze gates.

# 1.0.64 — Production freeze / release candidate

- Seed hotfix: adds an explicit `--allow-mixed-scale-seed` test-only override so realistic/benchmark DEMO/RDEMO fixtures can be added beside existing test masters while refusing any target month that contains non-DEMO Internal attendance/payroll history.

- Freezes the SESCCO MS Payroll integration sequence after the 1.0.58 frontend/backend action-parity, 1.0.59 server data-authority, 1.0.60 output E2E, 1.0.61 scale-seed, 1.0.62 performance, and 1.0.63 production-E2E certification upgrades.
- Adds `merge/release-candidate.json` and `scripts/verify-release-candidate.py` to bind the final release identity, the exact 1.0.63 predecessor archive checksum, required static/runtime gates, supported seed profiles and canonical deployment entrypoint.
- Carries the frozen Payroll production-E2E contract forward to release 1.0.64 and requires the release-candidate verifier from both the packaged production-freeze gate and the production release-task pipeline.
- Updates Payroll static cache-busters and package documentation to 1.0.64 without changing Payroll formulas, database schema, lifecycle semantics, permissions or user-facing workflow behavior.
- Runtime certification remains mandatory in the isolated Docker/PostgreSQL rehearsal environment: deployment checks, zero migration drift, the curated Payroll E2E Django suite, and the full Django regression suite must pass before production cutover.
- Regenerates the complete source/configuration SHA-256 production freeze after all final release metadata and verification changes.

# 1.0.63 — Full Payroll production E2E certification

- Adds a single frozen production-E2E certification contract at `merge/payroll-production-e2e.json` spanning 11 high-risk scenarios and 75 critical existing Django regression tests across Internal Payroll, Rental Manpower, Documents and platform access boundaries.
- Adds `scripts/certify-payroll-production-e2e.sh`, which first verifies the frozen certification contract, then runs `check --deploy`, rejects migration drift, and executes the curated 13-label Django Payroll suite against Django's isolated test database.
- Certification coverage explicitly includes owner/officer authorization and forbidden access, attendance status normalization/submission, payroll review/approval integrity, WPS/payment reconciliation, Rental assignment/timesheet/settlement/payment workflows, invalid transitions, lifecycle/archive/delete/restore recovery, reports/documents, tenant isolation, benchmark seed shape and performance regression guards.
- Adds `scripts/verify-payroll-production-e2e.py` and a Django contract wrapper. The static verifier fails if a required scenario loses its referenced regression test, a prerequisite release verifier disappears, or the runtime/rehearsal certification path is removed.
- Wires the production-E2E contract into Payroll frontend verification, release tasks and the production-freeze gate. Production rehearsal now runs the dedicated certification suite separately and stores `payroll-e2e-certification.txt` as evidence before the full Django regression suite.
- No Payroll calculation formula, schema, or user-facing workflow is changed in this certification release. The 1.0.62 query hardening and 1.0.61 benchmark profiles remain intact.
- The package can statically verify certification completeness in environments without Django; runtime certification remains mandatory in the release/rehearsal environment where Django/PostgreSQL are available.

# 1.0.62 — Payroll performance & query hardening

- Converts the highest-cardinality Internal Payroll calculation sources from per-employee database access to set-wise locked loads for organization assignments, salary structures/lines, attendance entries and overtime snapshots while preserving the existing transaction and `SELECT FOR UPDATE` authority.
- Makes Internal Attendance roster rendering prefetch effective salary structures and salary lines so overtime readiness does not issue salary queries per employee; overtime save/submission validation also resolves effective structures and base components set-wise.
- Reworks Payroll calculation snapshot creation to validate generated line/component/adjustment objects in memory and persist them with bounded `bulk_create` batches. Snapshot fingerprint verification now fetches line children set-wise instead of querying components and adjustments for every Payroll line.
- Removes an O(workers × assignments) Rental Timesheet roster scan by grouping effective assignments by worker before segment construction.
- Hardens Rental settlement context by loading supplier scopes for all project-periods in one query and reusing the already-loaded adjustment set. Settlement snapshot lines/rates/adjustments are persisted in bounded batches and fingerprint verification groups child rows set-wise.
- Adds `python manage.py payroll_performance_report` with SQL query counting and elapsed-time diagnostics for Internal Attendance, Internal Payroll preflight, the largest Rental project timesheet and Rental settlement context. `--fail-on-query-budget` enforces the release query budgets (40 queries per measured Internal/Rental path by default).
- Adds `merge/payroll-performance.json`, `scripts/verify-payroll-performance.py` and a Django regression wrapper, and wires the static performance contract into the production-freeze gate so cardinality-dependent query patterns cannot silently return.
- Keeps the 1.0.61 functional/realistic/benchmark seed profiles unchanged. No schema migration is required; the high-volume query shapes use the existing Payroll indexes and uniqueness constraints.

# 1.0.61 — Large test & benchmark Payroll seed profiles

- Keeps the existing `functional` DEMO seed as the default and adds explicit `realistic` and `benchmark` volume profiles without changing production Payroll behavior.
- Adds a realistic profile with 250 Internal employees, 750 Rental workers, 6 branches, 12 departments, 8 suppliers, 12 projects and six months of scale history.
- Adds a benchmark profile with 2,000 Internal employees, 5,000 Rental workers, 15 branches, 24 departments, 30 suppliers, 40 projects and twelve months of scale history.
- Seeds high-cardinality daily Internal Attendance and Rental Timesheet rows, overtime, approved advances/adjustments, closed Payroll snapshots, WPS salary-payment rows, worker transfer history, supplier settlements, settlement lines and paid supplier-payment allocations.
- Uses stable `DEMO-SCALE-*` / `RDEMO-SCALE-*` identities, unique financial references, conflict-safe bulk inserts and post-seed population verification so interrupted large seeds can be resumed safely by rerunning the same profile.
- Makes scale seeding monotonic: `benchmark` expands an existing `realistic` dataset, while later smaller-profile runs never shrink or rewrite the larger benchmark history.
- Keeps the canonical functional Draft + closed E2E month separate from scale history so benchmark rows do not change the known workflow fixture used for functional testing.
- Blocks `realistic` / `benchmark` on a tenant containing non-DEMO Internal employees or Rental workers to prevent accidental benchmark pollution of production-like payroll data.
- Adds `--seed-profile functional|realistic|benchmark` to production deploy/release scripts, plus `IMS_SEED_PROFILE` and `IMS_SEED_BATCH_SIZE` operator controls.
- Adds a frozen scale-seed contract, regression coverage, operator documentation and a production-freeze verifier. No database migration is required.

# 1.0.60 — Payroll reports, WPS, payments and documents E2E completion

- Freezes the Payroll output path after the 1.0.58 action-parity and 1.0.59 data-authority upgrades: server-generated reports, Internal WPS/salary-payment reconciliation, Rental supplier settlement/payment finance, and immutable final documents are now covered by one release contract.
- Replaces the supplier-profile payment/document shortcuts with real finance drill-downs. Supplier payment rows open the authoritative payment detail, the Payments workspace opens pre-filtered to that supplier, and the supplier Documents tab renders actual finalized Django document records instead of static placeholder tiles.
- Makes report CSV export match the visible report search filter by sending the active search query to the backend export endpoint and filtering the authoritative server report rows before CSV serialization. Existing spreadsheet-formula neutralization remains in force.
- Adds `merge/payroll-output-e2e.json` and `scripts/verify-payroll-output-e2e.py`, covering 12 workspace/report routes, 6 Internal payment/WPS endpoints, 6 Rental settlement/payment endpoints and all 7 final document types.
- The output verifier rejects a return of the old supplier-settlement placeholder toast and enforces document eligibility gates: Locked timesheets, Approved-or-later settlements, and Paid payment receipts.
- Adds a Django `SimpleTestCase` wrapper for the output verifier and wires the gate into both Payroll frontend verification and the packaged production-freeze verification. Existing 80-mutation action parity, 30-key browser-storage authority, 67 URL contracts and complete DEMO report/WPS/document seed coverage remain intact.
- No database migration or payroll-calculation formula change is required.

# 1.0.59 — Payroll mutation and data authority completion

- Makes the browser explicitly a cache/render layer for Payroll business data; Django/PostgreSQL remains authoritative for masters, attendance/timesheets, payroll calculations, adjustments, settlements, payments, documents and lifecycle state.
- Adds generation-based stale-response protection for Internal Attendance, Internal Payroll, Salary Payments, Rental Timesheets and Rental Settlements. A slow GET that started before a newer server mutation is now discarded instead of overwriting the mutation result in browser memory.
- Hardens Salary Payments period switching so an older-period response may be cached but cannot replace the active period's payment/template/readiness arrays. Cached periods are re-activated deliberately when selected again.
- Hardens Rental Settlements the same way: period-specific settlement/financial snapshots remain cached by period, while active adjustment/payment/timesheet-scope arrays are only activated for the currently selected period.
- Captures Rental Timesheet project/period scope before loading and only re-renders when that same scope is still active, preventing late project/period responses from hijacking the visible sheet.
- Removes obsolete empty browser persistence placeholders for Rental Timesheets, Rental Overtime, Supplier Payments, Rental Worker state and Rental Settlements so future work cannot mistake them for supported persistence paths.
- Adds `merge/payroll-data-authority.json`, documenting the 30 allowed `payroll-ui-*` browser-storage keys. These are UI preferences/selections only; business ledgers and master records are forbidden from localStorage.
- Adds `scripts/verify-payroll-data-authority.py`, a Django regression wrapper, and production/frontend release gates that enforce browser-storage scope plus stale-response guards across the five authoritative domains.
- No database migration is required. Existing server-side lifecycle, calculation and payment semantics remain unchanged.

# 1.0.58 — Payroll frontend/backend action parity

- Adds a machine-readable Payroll mutation contract at `merge/payroll-action-parity.json` covering 80 user-triggered Internal Payroll, Rental Manpower, Documents and Payroll Settings mutations.
- Adds `scripts/verify-payroll-action-parity.py`, which proves every registered mutation still has visible client wiring, handler-bound `data-*` controls where applicable, a mounted Django backend function, and the exact POST/PATCH/DELETE method accepted by that function's `require_http_methods` contract.
- Extends the existing frontend verification beyond URL existence. The previous gate still verifies 67 browser URL contracts; the new gate additionally verifies 80 mutations against 73 backend method contracts and 40 bound action selectors.
- Explicitly protects multi-action workflow controls including attendance submit/return, payroll calculate/reset/review/approve/return, payment prepare/export/start/cancel/import/close/reopen/retry, Rental timesheet submit/return, settlement calculate/return/close, supplier payment result/retry, lifecycle Archive/Delete/Restore, and Archive/Delete-bin restore.
- Adds a Django regression test that runs the action-parity verifier inside the normal test suite and fails if high-risk Payroll actions leave the registry.
- Wires the action-parity gate into both `verify-payroll-frontend.sh` and the production-freeze verifier so a production-looking button can no longer ship merely because its URL happens to exist.
- No database migration or payroll calculation change is required; this upgrade hardens the UI-to-backend execution contract before the 1.0.59 mutation/data-authority pass.

# 1.0.57 — Archive/Delete/Restore cascading integrity

- Hardens the existing 30-day recoverable Delete model for Branch / Office, Department, Internal Employee, Manpower Supplier, Rental Worker and shared Project without turning historical payroll, attendance, timesheet, settlement, payment, inventory movement, document or audit records into destructive cascades. Parent-owned operational child masters continue to share the exact parent recovery window and restore atomically through `TrashCascadeLink`.
- Fixes lifecycle API recovery for independently restored child records. An Internal Employee restored while its Branch/Department parent is still deleted, or a Rental Worker restored while its Manpower Supplier parent remains deleted, now returns a successful payload with the inherited parent Delete state instead of re-querying only currently visible rows and reporting an error after the restore succeeded.
- Makes Project Archive/Delete an explicit inherited **assignment operational boundary** rather than falsely deleting the permanent Rental Worker master. Current effective-dated assignments remain intact for history/recovery; worker payloads now publish project lifecycle/operational state and assignment payloads retain project identity even when the deleted project is absent from the active project directory.
- Updates the Rental Worker profile so a deleted/archived/on-hold project is shown as a retained assignment boundary. Transfer and Release remain available for safe recovery/redeployment, while project-local Trade/Rate changes are suppressed until the project is active again. Deleted projects are not exposed as broken profile links.
- Corrects an outdated Internal API regression test that expected Department Delete not to soft-delete its current employee child; the test now enforces the same parent/child `deleted_at` and `purge_after` window used by the production service. Adds explicit API regressions for independent child restore under a deleted parent and a Rental project delete/restore regression proving the worker master and exact assignment survive.
- Extends the packaged Payroll contract gate so future releases fail if inherited child recovery, project assignment lifecycle authority, or exact cascade test coverage is removed. No database migration is required.

# 1.0.56 — Rental Manpower lifecycle completion

- Makes the Rental settlement/project lifecycle backend-authoritative from locked timesheet through calculation, review, approval, supplier payment, and project-period closure. Project contexts now publish `allowedActions`, `nextAction`, and explicit action gates; the browser no longer derives settlement actions from display labels.
- Makes supplier-payment result handling backend-authoritative. Payment rows now publish allowed result actions, retry eligibility, and receipt eligibility; the UI consumes those permissions for Paid/Failed/Cancelled/Reversed transitions and retry instead of inferring them from status text.
- Advances `SupplierSettlement.revision` on review submission, return/rejection, approval, payment-status synchronization, and closure in addition to calculation, preserving a complete authoritative state-change sequence for downstream finance/document workflows. Canonical service aliases such as `submit_for_review`, `return_for_changes`, `close_period`, and payment result `complete` are accepted without changing stored lifecycle values.
- Tightens Return for Changes so a project settlement group can only return when every supplier snapshot is in Review, preventing a mixed-state project group from partially rewinding.
- Preserves historical finance completion after operational stop boundaries: terminating a supplier/worker or completing a project continues to block new operational assignments while already-approved settlement snapshots remain payable, documentable, reversible/retryable where allowed, and closable.
- Confirms supplier invoice generation remains limited to Approved-or-later settlement snapshots and supplier payment receipts remain limited to Paid supplier payments; those document checks stay server enforced.
- Extends the settlement progress display through Payment and Closed states and removes the unused browser `rentalSettlementHasDrift()` placeholder that falsely hardcoded no drift. Adds regression/static release coverage for lifecycle authority, revisions, document gates, and historical-finance continuity.
- No database migration is required.

# 1.0.55 — Internal Payroll lifecycle completion

- Makes the Internal Payroll Run workflow backend-authoritative from calculation through review and approval. The period context now publishes allowed actions and explicit `canCalculate`, `canReset`, `canSubmitReview`, `canReturnForChanges`, and `canApprove` gates; the browser renders actions from that contract instead of inferring permission from display labels.
- Advances `PayrollRun.revision` on every authoritative lifecycle mutation: calculation/recalculation, reset, review submission, return/rejection, approval, payment-processing start, Paid transition, Close, and Reopen. Workflow aliases such as `submit for review` and `reject` normalize at the service boundary without changing stored statuses.
- Makes salary-payment batch actions backend-authoritative. Payment responses now publish `allowedActions`, `nextAction`, and row-level `canRetry`; the UI consumes those fields for Start, Import Results, Retry, Close, Cancel, and Reopen.
- Exposes the existing controlled Cancel Batch and Reopen Payroll services in the production UI. Both reason-required transitions remain server validated; cancellation is limited to Prepared/Exported batches and reopen is limited to Closed batches.
- Fixes stale Payroll Run state after payment processing by invalidating the selected-period payroll context whenever salary-payment state changes, forcing the next Payroll Run view to reload the server status instead of retaining an older Approved snapshot in browser memory.
- Adds service/selector regression coverage for the complete approval and payment chains plus a packaged frontend contract that rejects a return to display-status action inference or loss of lifecycle authority.
- No database migration is required.

# 1.0.54 — Attendance/status contract hardening

- Introduces one backend Payroll attendance contract shared by Internal Attendance and Rental Manpower Timesheets for allowed hours, explicit status codes, text aliases, workflow states, and canonical workflow actions. Blank remains the only incomplete attendance value; numeric 0–24 hours and every supported explicit status are complete values for Submit/Approve/Lock validation.
- Internal Attendance exposes `A` Absent, `L` Leave, `S` Sick, `H` Holiday, and `OFF` through the backend contract. Rental Timesheets expose `A` Absent, `N` No Scope, `L` Leave, and `OFF`. API/import values such as `absent`, `holiday`, `no scope`, `off day`, and `present` normalize at the service boundary instead of relying on browser translation.
- Publishes the authoritative attendance contract in Internal attendance responses and Rental master/timesheet contexts. The browser now normalizes inputs, renders legends/help text, and enables workflow actions from that server contract rather than maintaining separate hard-coded code lists.
- Makes Internal and Rental workflow action aliases converge on `submit`, `approve`, `lock`, and `return_to_draft`; `submit_for_review`, `return`, and `reject` remain accepted service-boundary aliases. Rental revision numbers now advance on Submit, Approve, and Lock as well as correction returns so downstream settlement snapshots have a precise source revision.
- Corrects the Rental bulk controls so `A` is Absent and numeric `0` is Zero hours, and exposes Leave/Off bulk actions. Valid alphabetic attendance statuses no longer appear as invalid merely because they are letters; unsupported text still fails with a controlled validation message.
- Extends DEMO Internal attendance so the seeded grid includes Holiday in addition to Absent, Sick, Leave, Off, and worked-hour rows. Existing Rental DEMO data already covers Absent, No Scope, Leave, Off, and worked-hour rows.
- Adds shared-contract, Internal alias/submission, Rental alias/reject/revision, seed, and packaged frontend authority regression guards. No database migration is required.

# 1.0.53 — Server-side Payroll directory authority

- Moves the six Payroll master registers—Branches / Offices, Departments, Internal Employees, Rental Projects, Manpower Suppliers, and Rental Workforce—onto company-scoped backend search/filter/sort/pagination APIs instead of filtering the visible register from browser master arrays.
- Adds reusable browser directory loading with stale-response protection, loading/error/retry states, backend result counts, Previous/Next navigation, and 25/50/100 row page sizes while preserving existing profile/action navigation.
- Extends Internal organization endpoints with server-derived employee counts and employee-count sorting. Employee list responses now carry selected-period payment-profile/WPS state so WPS filters and row badges use the same backend authority.
- Extends Rental directory APIs with project↔supplier filters, payment-term/workforce/outstanding supplier filters, project client/manager filters, and worker operational-status/project/trade/rate-type filters. Project and supplier rows retain the 1.0.51 settlement financial authority for the selected period.
- Stops embedding the duplicate all-employee organization-history map in the Payroll shell; organization history is loaded with the selected employee profile. Register mutations invalidate the affected server directory so create/edit/lifecycle/transfer/restore actions do not leave stale pages.
- Adds Internal and Rental API regression coverage plus a packaged release contract that rejects removal of server directory pagination or a return to client-side register filtering.
- The shell still retains compact master/reference data used by cross-workspace summaries and workflow pickers; the register rows themselves are server-paginated. Shell-wide reference-cache sizing remains part of the final performance/freeze pass rather than being coupled to this functional cutover.
- No database migration is required.

# 1.0.52 — Internal employee profile backend authority

- Replaces the Internal Employee profile's browser placeholders for overtime, Payroll History, and Recent Activity with a dedicated company-scoped backend profile endpoint.
- Current-period attendance/OT now reads persisted Attendance entries and overtime snapshots; the browser keeps live attendance as a temporary fallback only until the authoritative profile payload arrives.
- Payroll History now reads immutable `PayrollRunLine` snapshots and exposes the related payment state/reference when a salary-payment row exists, so historical payroll no longer appears empty after real runs.
- Recent Activity now reads append-only Internal Payroll audit events related to the employee, organization/salary changes, adjustments, attendance periods, payroll runs, salary-payment batches/rows, and payment-profile changes instead of manufacturing status messages in the browser.
- Adds mutation-aware profile-cache invalidation after attendance/OT, workflow, payroll, payment, salary, organization, lifecycle, and employee master changes.
- Adds selector/API regression coverage plus a packaged frontend/backend authority contract that rejects the former `otHours: 0`, `payrollHistory: []`, and `activity: []` placeholders.
- No database migration is required.

# 1.0.51 — Rental financial authority

- Replaces Rental Project/Supplier financial zero placeholders with authoritative period aggregates from immutable supplier settlement snapshots and supplier-payment allocations.
- Connects project lists, supplier lists, project profiles, supplier profiles, Rental overview controls, and selected-period refreshes to the same backend financial metrics for regular/OT hours, gross/net cost, advances, paid, processing, and outstanding.
- Preserves current workforce/deployment counts from effective-dated assignments while retaining historical financial scopes after worker transfer or release.
- Separates calculated settlement cost from payable exposure: Draft/Calculated settlements contribute cost, but payable/outstanding/available remain zero until Approved or a later payable state.
- Adds reconciliation regression coverage and a release-time static contract that rejects a return of Rental financial zero placeholders or browser-only cost authority.
- No database migration is required.

# 1.0.50 — Idempotent DEMO history-period selection

- Fixes a second or later `./scripts/deploy-production.sh --seed` run failing with `Unable to find a collision-free DEMO history month before existing non-DEMO employment` after the 1.0.48 workflow-ready lifecycle fixtures had already been created.
- Root cause: `_safe_history_period()` used the latest joining date from **every** `DEMO-*` Internal Employee as the lower bound for the closed historical month. Current-period lifecycle fixtures such as `DEMO-190` / `DEMO-192` intentionally join in the live Draft month, so after a successful seed they made the previous closed month look invalid on the next idempotent run.
- Historical period selection now derives its DEMO lower bound only from the 18 base Internal Payroll seed employees (`DEMO-101…DEMO-118`) that actually participate in the finalized historical payroll. Lifecycle/cascade fixtures remain current-period-only and no longer influence historical-month discovery.
- Keeps the non-DEMO safety boundary intact: the history month still must precede real employee employment and remain free of non-DEMO attendance/payroll rows. This change does not relax production payroll isolation.
- Adds static and Django contract coverage so the broad `DEMO-*` lower-bound query cannot return and the historical cohort remains exactly aligned with `INTERNAL_EMPLOYEES`. No database migration or reseeding cleanup is required.

# 1.0.49 — Payroll Run review UI + calculation-detail integrity

- Fixes the Payroll Run header action group wrapping the final **Approve Payroll** action onto a second desktop row. Wide desktop layouts now keep lifecycle actions together; medium layouts intentionally stack the header before controls become cramped.
- Fixes the Review status card text collapsing word-by-word. The V2 bridge previously applied a three-column grid to a two-child DOM, squeezing the full status copy into a 34px column; the review card now maps to its real `copy + snapshot` structure.
- Converts employee Payroll calculation opening into a true **read-only Payroll Run detail** drawer. The drawer is labeled `Payroll run`, does not expose the generic Quick Add footer, and can no longer leak a stale `Create component` action from Salary Setup.
- Makes the native `hidden` state authoritative for Payroll drawer save/footer controls so author CSS cannot accidentally display hidden actions. This also hardens other readonly Payroll drawers.
- Fixes `Total deductions` in the calculation detail drawer producing `SAR NaN` when server snapshot amounts are serialized as decimal strings. Advance recovery and other deductions are normalized to numbers before summing.
- The detail drawer now explicitly reads the same server-authoritative row used by Payroll Register / Review and shows a compact Basic / Allowances / Overtime / Other Earnings reconciliation strip before the saved salary-component snapshot.
- Adds frontend contract checks for readonly Payroll details, numeric deduction reconciliation and shared snapshot sourcing. No database migration is required.

# 1.0.48 — Workflow-ready Internal + Rental current-period seed

- Fixes the seeded September Internal Attendance period being blocked at **Submit for Review** by 36 genuinely missing rows. The status letters were not the problem: `A`, `L`, `S`, `H` and `OFF` are valid explicit attendance values. The missing rows came from lifecycle fixtures created after the original 18-employee attendance grid (`DEMO-190` added 30 required days and `DEMO-192` added 6 employed days).
- The DEMO seed now performs a final current-period readiness pass after lifecycle fixtures. It fills **only missing** required cells, preserves tester-entered attendance, validates the Draft with the same production submission authority, and provisions the current lifecycle employees with salary structures and verified synthetic WPS destinations so later Payroll Run / WPS testing is not blocked.
- Repairs lifecycle fixtures created by 1.0.47 and earlier so `DEMO-190` / `DEMO-192` are current-period fixtures instead of retroactively entering already-finalized DEMO history. Fresh fixtures now start in the live Draft month.
- Rental Manpower was already seeded with 30 `RDEMO-001…030` workers on `DEMO-DIRIYA`; the apparent empty state came from the UI defaulting to the newer lifecycle project `DEMO-YARD`. A new project chooser defaults to the usable non-archived project with the largest active rental workforce while preserving a valid user-selected project.
- Completes current Rental Timesheet data **after** transfer/termination lifecycle fixtures are created. Missing assigned days for `RDEMO-090`, `RDEMO-092`, `RDEMO-093` and related current DEMO assignment segments are populated only where blank, so every seeded current DEMO project is ready for Draft → Submitted → Approved → Locked testing.
- Adds a shared Rental Timesheet completeness validator and revalidates at Submit, Approve and Lock. `A` = Absent, `N` = No Scope, `L` = Leave and `OFF` are valid explicit statuses; only missing assigned worker-days block the workflow.
- Corrects the Rental attendance legend (`0` is zero hours, not Absent; `A` is Absent, not Sick absence) and makes both Internal and Rental helper text explicitly distinguish valid status codes from blank/missing cells.
- Adds regression coverage for mixed explicit status-code submission and approval-time Rental completeness revalidation. No database migration is required for this release.

# 1.0.47 — Nullable-safe tenant reconciliation

- Fixed the production reconciliation false positive that reported `rental_manpower.SupplierPayment.retry_of` as a cross-company reference when `retry_of` is legitimately NULL on an original supplier payment.
- Internal Payroll and Rental Manpower reconciliation now validate company ownership only when a nullable company-owned relation is actually populated; real cross-company references are still rejected.
- Added SupplierPayment model validation so an actual retry link must remain inside the same company and supplier and cannot self-reference.
- Added runtime regression coverage around original-payment + retry reconciliation and a packaged static tenant-reconciliation contract.
- No database migration is required for this release.

# 1.0.46 — E2E cascade seed state-refresh fix

- Fixes `./scripts/deploy-production.sh --seed` falsely reporting that the Branch / Office cascade did not place its employee in the same 30-day recovery window after the PostgreSQL lock fix.
- Root cause: the lifecycle service correctly refetches and locks its own parent model instance, then updates that instance during Delete. The seed kept an older caller-held `deleted_branch` object and compared the freshly deleted child against the stale parent's pre-delete `purge_after=None`.
- Refreshes Branch / Office, Department and Manpower Supplier parent fixtures from the database immediately after their real Delete action before verifying the parent/child `deleted_at` and `purge_after` recovery window.
- Keeps the production cascade implementation unchanged; existing service regression tests already assert exact parent/child delete timestamps and 30-day recovery deadlines.
- Adds a static release gate so all three E2E cascade assertions must refresh their parent record before comparing recovery-window state. No schema or migration change is required.

# 1.0.45 — PostgreSQL cascade-lock compatibility

- Fixes `./scripts/deploy-production.sh --seed` failing during the Branch / Office lifecycle fixture with PostgreSQL `FOR UPDATE is not allowed with DISTINCT clause`.
- Root cause: Branch and Department 30-day cascade Delete locked `InternalEmployee` rows through a reverse organization-assignment join and then called `.distinct()`. PostgreSQL rejects `SELECT DISTINCT ... FOR UPDATE`, even though the cascade itself is valid.
- Keeps row-level locking and the 30-day recoverable cascade semantics intact. The service now resolves current employee ids through `EmployeeOrganizationAssignment` first, then locks the unique `InternalEmployee` rows with `SELECT ... FOR UPDATE` on the outer employee query, with deterministic primary-key ordering.
- Applies the same correction to both Branch / Office and Department Delete so the same production-only failure cannot appear later in the seed or normal lifecycle UI.
- Adds a release gate that rejects any future reintroduction of `DISTINCT` into these PostgreSQL row-locking cascade functions. No schema or migration change is required.

# 1.0.44 — Payroll E2E seed payment chronology fix

- Fixes `./scripts/deploy-production.sh --seed` failing while creating the closed Rental Payroll history with `Payment date cannot be earlier than the settlement approval date`.
- Root cause: the DEMO history is intentionally seeded for the prior closed month, while the real settlement approval transition happens at seed runtime. The fixture incorrectly forced the supplier payment date to that prior month-end, violating the production chronology guard.
- Keeps the production payment rule unchanged. Seeded Paid supplier payments now use the later of the historical period end and the actual settlement approval date, while still rejecting future Paid dates.
- Adds regression coverage for both chronology cases and keeps supplier-payment reports/documents attached to the historical settlement period through their allocation relationship.

# 1.0.43 — Working Actions + recoverable cascade delete + E2E seed verification

- Fixes the Payroll **Actions** dropdown regression on Branch / Office, Department and other lifecycle menus. The delegated controller correctly toggled the dropdown host, but a global CSS hardening rule still disabled pointer events on the menu itself; the open host now explicitly owns menu interactivity and the 1.0.43 assets are cache-busted.
- Adds explicit 30-day cascade-recovery ownership with `core.TrashCascadeLink`. Parent Delete now soft-deletes the exact operational child masters in the same recovery window and parent Restore atomically restores only those children. Independently deleted children are never resurrected by a parent restore.
- Branch / Office and Department Delete now soft-delete their current Internal Employee masters; Manpower Supplier Delete soft-deletes its Rental Worker masters; Project Delete soft-deletes its project Inventory Location and Stock Item masters. Effective-dated assignments, finalized payroll, attendance, settlements, stock movements, generated documents and audit evidence remain protected historical records.
- De-duplicates cascade-owned employees/workers from the Payroll Delete recovery page so users restore the parent boundary once instead of restoring children independently. Inventory Trash similarly hides project-owned cascade children and restores a deleted Project through the project service so its inventory scope is recovered atomically.
- Extends `--seed` lifecycle fixtures to execute real Branch, Department and Supplier cascades and verify child recovery deadlines. The full test seed now fails unless all Payroll report/WPS paths return data and every generated Payroll document type exists for the finalized DEMO history period.
- Adds regression coverage for the parent/child delete window and project inventory cascade, updates retention authority/verification, and adds forward migration `core.0005_trash_cascade_link` without rewriting released migrations.
- Hardens recovery ownership against stale-link edge cases: independently restoring a cascaded child releases the old parent ownership immediately, parent restore requires the original delete/purge window, and expired children retire cascade ownership before purge/tombstone retention. A later independent child delete can therefore never be resurrected or hidden by an older parent delete.

# 1.0.42 — Complete DEMO testing + stop/termination lifecycle

- Expands `--seed` into an idempotent end-to-end Payroll test dataset instead of only sample master rows. The seed now verifies Internal Payroll, Rental Manpower, management workforce cost, overtime, advances/adjustments, payments, transfers and WPS report output.
- Creates a collision-safe closed DEMO history month so approval, locked attendance/timesheets, payroll calculation, supplier settlements, payment workflows and finalized output documents can be exercised without mixing non-DEMO employees into the synthetic finalized payroll.
- Exercises the full Internal salary-payment/WPS lifecycle: company payment settings, verified employee payment destinations, configurable WPS CSV template, batch preparation, export, processing, result import, Paid reconciliation, close, salary slips and salary-payment receipts.
- Exercises Rental settlement output end to end: timesheet + overtime, approved adjustment, calculated/reviewed/approved settlement, paid supplier payment, supplier invoice, settlement document, payment receipt and closed settlement.
- Seeds deterministic lifecycle records for Active, On Leave, temporary Stop, Terminated, Archived and 30-day Delete states, together with transfer/rate-change, On Hold and Completed project scenarios.
- Adds explicit temporary **Stop activity** versus final **Termination** semantics for Internal Employees, Rental Workers and Manpower Suppliers. Temporary stop can be resumed and keeps history; termination is final for that employment/worker/supplier relationship and blocks new operational activity while retaining historical payroll, assignments, timesheets, settlements, payments and documents.
- Supplier termination cascades termination through its current worker scope and safely closes/cancels editable assignment activity where possible. Protected submitted/approved/locked history is retained rather than rewritten.
- Makes rental timesheet lifecycle checks effective-date aware so historical draft corrections through a stop/termination date remain possible while new activity after that date is blocked.
- Adds `rental_manpower.0008_supplier_worker_termination` for supplier stop metadata plus supplier/worker termination dates/reasons and terminated status constraints; no previously released migration is rewritten.
- Updates Supplier and Rental Workforce filters/profile actions for Terminated state and keeps termination out of ordinary master Edit flows. New Internal Employees are no longer created directly as Terminated; termination is an explicit lifecycle action.
- Adds release verification for comprehensive DEMO coverage and stop/termination authority, and bumps Payroll frontend assets to `1.0.42`.

# 1.0.41 — Reversible lifecycle cascade

- Makes Archive and 30-day Delete intentionally less restrictive for the operational masters requested: Branch / Office, Department, Internal Employee, Manpower Supplier, Rental Worker and shared Project.
- Branch / Office and Department lifecycle now cascades operational visibility to employees through the existing current effective-dated organization assignment. Employee rows, employment status and payroll history are not rewritten. Restoring the parent immediately restores only the inherited employee scope.
- Internal employee and rental worker register filters now treat inherited parent lifecycle as a real cascade: ordinary lists exclude children whose current Branch / Department / Supplier is archived or deleted, while Archive/Delete views can surface that inherited state without rewriting the child master.
- Manpower Supplier Archive/Delete now cascades to its worker operational scope without rewriting worker status or assignment history. Workers whose supplier is archived/deleted are rejected from new assignments, timesheet edits and new settlement adjustments until the supplier is restored.
- Individual Internal Employees and Rental Workers may now be archived or soft-deleted while Active; Archive/Delete no longer forces a separate stop/inactive transition. Their historical payroll/assignment records remain intact.
- Project Archive/Delete no longer requires zero stock or released Rental Manpower assignments. Existing project inventory and rental assignment scope becomes non-operational with the project and returns on restore. Project completion remains strict and still requires stock/assignment closeout.
- Adds `Project.archive_previous_status` so project Archive/Restore returns to the exact prior Active / On Hold / Completed state instead of guessing a safe status.
- Adds forward migrations `internal_payroll.0012_reversible_archive_lifecycle` and `projects.0006_project_reversible_archive_state`; no previously released migration is rewritten.
- Keeps Delete recoverable for 30 days and deliberately avoids destructive database cascade. Protected payroll, attendance, assignment, settlement, inventory movement, finalized-document and audit evidence can never be erased merely because a parent master was deleted.
- Updates Archive/Delete screens and Actions hints to describe the reversible cascade and removes old dependency-clearance guidance.

# 1.0.40 — Organization Actions dropdown visibility + lifecycle label cleanup

- Fixes the Branch / Office and Department directory **Actions** control that appeared unresponsive even though the delegated click handler was running: the dropdown was opening inside a generic payroll panel with `overflow: hidden`, so the entire menu was clipped.
- Makes organization-master detail cards allow lifecycle overlays and opens their footer Actions menu upward, while keeping profile/header Actions menus in their existing placement.
- Keeps the shared delegated dropdown controller and server-authoritative lifecycle handlers unchanged; this is a presentation/interaction repair rather than a lifecycle-rule change.
- Renames the Payroll lifecycle navigation from **Archive Bin** to **Archive** and from **Trash Bin** to **Delete**.
- Cleans the visible lifecycle copy so Delete is described as a **30-day recovery** operation instead of exposing the internal Trash/Bin terminology.
- Archive and Delete remain separate operations. Deleted employee, branch/office, department, supplier, worker and project masters remain recoverable for 30 days; protected payroll, assignment, inventory and audit history is still retained.
- Bumps Payroll frontend cache-busters to `1.0.40` so the repaired CSS/JS cannot be masked by a cached 1.0.39 asset.

# 1.0.39 — Record lifecycle actions, 30-day Trash, and SESCCO MS shell branding

- Fixes the dynamically rendered Payroll **Actions** dropdown by moving dropdown open/close behavior to a delegated document-level handler; profile Actions controls now work after route rendering and re-rendering.
- Separates **Archive** and **Delete** as explicit Actions-menu operations instead of mixing them into edit/employment/status forms.
- Adds 30-day soft-delete Trash retention to Internal Employees, Branches / Offices, Departments, Manpower Suppliers and Rental Workers; shared Projects continue on the same 30-day Trash contract.
- Adds dedicated **Archive Bin** and **Trash Bin** Payroll routes with restore actions for Internal Company and Rental Manpower records.
- Delete now means **Move to Trash**. Records are hidden from active selectors immediately, remain recoverable for 30 days, and keep the deletion actor/reason/purge deadline for auditability.
- Keeps historical payroll, attendance, organization assignments, rental assignments, settlements, payments, inventory and audit evidence intact while a master is archived or in Trash.
- Hardens Trash expiry: a physical delete is allowed only when Django's deletion collector proves that no related row would be cascaded or protected; otherwise the expired item becomes a hidden historical tombstone instead of deleting history.
- Adds restore-from-Trash backend actions and audit events for employee, branch/office, department, supplier, worker and project masters.
- Adds forward migrations `internal_payroll.0011_master_trash_retention` and `rental_manpower.0007_master_trash_retention`; no previously released migration is rewritten.
- Locks the product shell identity to **SESCCO MS — Management System** so an environment override cannot restore the old “Project Inventory” brand label.
- Extends production lifecycle verification and frozen migration/source manifests for the new retention contract.

# 1.0.38 — Immutable branding-migration lineage repair

- Repairs the production failure `column core_company_settings.document_branding_mode does not exist` seen after migrations completed and the `--seed` phase started.
- Restores `core.0003_company_document_branding` to the exact migration that originally shipped and may already be recorded as applied in production; previously released migrations are no longer rewritten.
- Adds forward-only `core.0004_company_document_branding_lineage_repair`, which idempotently adds the missing branding-mode database column when needed and safely accepts databases where it already exists.
- Reconciles both known database lineages by preserving/widening branding file columns to 180 characters, enough for SESCCO branding storage keys.
- Restores the 12 MB branding upload-size validator while keeping the current logo / letterhead / watermark storage layout and extension checks.
- The repair preserves existing company settings and existing branding file references; it does not delete or rewrite uploaded branding assets.
- Adds a frozen migration-lineage verifier so an already-released migration cannot be silently edited again.
- Adds a post-migration physical-schema gate before `--seed`, so migration-recorder/schema divergence fails with a direct release error instead of an ORM traceback.

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
