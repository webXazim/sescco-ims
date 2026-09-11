# SESCCO IMS 1.0.12

## Inventory Explorer control density and dropdown convergence

- Converted Inventory Explorer More Filters and Columns controls to accessible icon-only triggers, reclaiming horizontal space for search.
- Expanded the Inventory Explorer search field to consume available desktop space while preserving clean responsive wrapping.
- Converged native Inventory/Payroll selects and floating dropdown panels on the Condition dropdown visual language.
- Preserved existing filtering, saved-view, column-selection, keyboard and accessibility behavior.
- No database migration or production-data rewrite is required.

# SESCCO IMS 1.0.11

## Inventory Explorer compact filter-row polish

- Reworked the Inventory Explorer filter toolbar so the search field stays intentionally compact on desktop instead of consuming an entire row.
- Kept search, location, condition, stock status, date, sort, More filters and Columns aligned in one balanced desktop toolbar whenever the available width permits.
- Replaced the always-visible New / Used / No value checkbox stack with a compact Condition dropdown while preserving multi-condition filtering and saved-query compatibility.
- Condition selections refresh the live inventory results immediately, update the dropdown label, and support Clear / Done controls plus click-outside and Escape dismissal.
- Added responsive fallbacks so the toolbar wraps cleanly on narrower screens and the condition menu becomes a safe mobile sheet.
- Added a production freeze verifier for the Inventory Explorer filter composition. No schema migration or business-data rewrite is required; deploy with `./scripts/deploy-production.sh`.

# SESCCO IMS 1.0.10

## Payroll dropdown control-height correction

- Fixed the remaining legacy CSS-specificity conflict that allowed Payroll compact selects to fall back to 30–32px even after the shared 1.0.9 select-control upgrade.
- Standard Payroll and Inventory select controls now use a deterministic 40px production control height with aligned text, chevron spacing, radius and focus geometry.
- Payroll filter selects, including Rental Project Timesheets project/supplier filters, now visually align with the search and action controls instead of appearing as thin inline chips.
- Internal/Rental timesheet Day selectors use a 38px control height so the command strip remains compact without becoming too thin.
- Dense import/staging and pagination selects remain intentionally compact at 34px to preserve table geometry.
- No schema migration or business-data rewrite is required; deploy with `./scripts/deploy-production.sh`.

# SESCCO IMS 1.0.9

## Unified dropdown controls and today-aware timesheet day

- Standardized native select/dropdown controls across the Inventory and Payroll application shells with one shared premium control treatment: consistent chevron, border, radius, spacing, hover/focus/disabled states and compact timesheet geometry.
- Kept native `<select>` semantics and keyboard/accessibility behavior while removing browser-default visual mismatches from Payroll filters, timesheet filters, Inventory forms and project/supplier controls.
- Internal and Rental timesheet bulk-day selectors now initialize to the company-local current day whenever the viewed period is the current month. The current-day option is labelled `Today`.
- Changing the timesheet period recalculates the preferred day: current month selects today; another month starts at day 1. Manually choosing a different day remains respected during ordinary rerenders.
- Added a production verifier for the shared dropdown stylesheet and today-aware timesheet state. No database migration or business-data rewrite is required; deploy with `./scripts/deploy-production.sh`.

# SESCCO IMS 1.0.8

## Required-field UX and session-message hardening

- Added one shared required-field contract across Inventory, Projects, authentication forms and all Payroll workspaces. Required controls render a visible red `*` from the actual validation contract instead of relying on placeholder text.
- Empty required controls are highlighted in place with a red border and inline `Required` indicator; the first missing control is focused and scrolled into view. The indicator clears as soon as the value is corrected.
- Added Payroll drawer validation for Internal Company, Rental Manpower and Management workflows, including conditional requirements such as terminated-employee end dates, completed-project end dates, payment references, review notes and payment destinations.
- Preserved server-side validation as the authority while adding the same visual error state to server-rendered Django form errors.
- Replaced the technical `Authentication is required.` API message with a clear sign-in-session message so an expired session is no longer confused with a missing business-form field.
- Added production verification and gateway smoke coverage for the shared validation CSS/JavaScript. No schema migration or business-data rewrite is required; deploy with `./scripts/deploy-production.sh`.

## 1.0.7 — Payroll dropdown interaction hotfix

- Fixed V2 Payroll dropdown menus that were visible but still had `pointer-events: none`, causing clicks to pass through to controls beneath the menu.
- Aligned dropdown interaction with the existing controller contract: `.is-open` lives on the parent `[data-dropdown]`, while the child menu becomes interactive only when that parent is open.
- Raised the active dropdown stacking context so Business, Business Area, Payroll Workspace, Account and topbar menus remain interactive above page content.
- Added a production verification guard for the dropdown pointer-event contract.

No migration or production-data change is required. Deploy with `./scripts/deploy-production.sh`.

## 1.0.6 — Payroll workspace navigation hotfix

- Replaced the Internal / Rental / Management workspace menu's JavaScript-only buttons with real reload-safe Payroll URLs.
- Added server-side validation of the requested Payroll workspace against the active company membership before publishing it to the browser bootstrap.
- Made the request-specific authorized workspace list authoritative in the browser instead of re-deriving permission from the generic role matrix.
- Persisted the active workspace in the URL and retained localStorage only as a convenience fallback.
- Made same-hash workspace switches redraw immediately, so switching to another workspace while already on `#/overview` cannot appear to do nothing.
- Decoupled workspace-switch event binding from sidebar resize/collapse initialization and aligned Management drill-down/global-search transitions with the same URL state.
- No schema migration or production-data rewrite is required. Deploy through the existing `./scripts/deploy-production.sh` pipeline.

# SESCCO IMS 1.0.5

## Static manifest bootstrap ordering hotfix

- Fixed production cutover failure under `ManifestStaticFilesStorage` when a newly referenced Payroll/Platform asset was not yet present in `staticfiles.json` during the pre-cutover Payroll template render.
- `collectstatic --noinput` now runs before `payroll_bootstrap_report --fail-on-errors`, while retaining previous release assets so the currently serving web release remains safe during cutover.
- Applied the same ordering to the isolated production rehearsal path so a clean rehearsal static volume can render Payroll templates correctly.
- Added release verifiers that reject any future regression where Payroll bootstrap rendering occurs before static collection.
- Extended the post-cutover gateway smoke test to cover the new Inventory shell CSS/JS and Payroll shell-fix CSS.
- No database migration or business-data change is required; the canonical deployment command remains `./scripts/deploy-production.sh`.

# SESCCO IMS 1.0.4

## Unified Inventory/Payroll shell and true timesheet focus mode

- Fixed Payroll Attendance & Overtime full-screen mode so the V2 sidebar, topbar, mobile scrim and collapsed-rail control are completely removed while the timesheet owns the full viewport.
- Removed the V2 workspace sidebar offset and clipping during focus mode, so the sheet starts at the physical left edge instead of remaining constrained to the content column.
- Moved Inventory onto the same light, compact navigation language as Payroll: matching 236px rail, 64px collapsed state, typography, active/hover states, business/area controls and account treatment.
- Added Inventory sidebar collapse, drag-to-resize, keyboard resize and persisted width/state without changing Inventory URLs, page forms or backend behavior.
- Replaced the Inventory navigation glyph characters with consistent SVG line icons and aligned the Inventory top rail/search controls with the Payroll shell.
- The canonical production deployment command remains `./scripts/deploy-production.sh`; no database migration is required for this UI/shell release.

# Project Inventory 1.0.3

## PostgreSQL Payroll row-lock hotfix

- Fixed the production Payroll bootstrap failure caused by applying unrestricted `SELECT ... FOR UPDATE` to nullable `select_related()` joins on attendance workflow users.
- Scoped the attendance-period row lock to `AttendancePeriod` itself, preserving the workflow-user joins without asking PostgreSQL to lock the nullable side of the outer join.
- Applied the same lock scoping to the Payroll Run workflow because its nullable `attendance_period` relation had the same latent PostgreSQL failure mode during review/approval transitions.
- No schema migration or production data rewrite is required; this is a query/locking correction only.
- The existing `./scripts/deploy-production.sh` deployment workflow remains canonical.

## Project Inventory 1.0.2

## Platform shell and Payroll production hotfix

- Reworked the shared Business and Area switchers into compact navigation controls instead of oversized sidebar cards.
- Replaced the Inventory footer's inline username/sign-out treatment with a consistent account drop-up and simplified the Payroll account trigger.
- Made the shared 500 page module-neutral so Payroll failures no longer display stock-specific wording.
- Kept `scripts/deploy-production.sh` as the canonical deployment command and made it verify the production source freeze directly.
- Added a production-data Payroll bootstrap render gate to `scripts/release-tasks.sh`; deployment now exercises `/app/payroll/` against active company data before replacing the live web container and prints the full traceback if bootstrap rendering fails.

## Production-readiness hotfix

- Standardized host deployment verification on the documented `python3` command.
- Fixed invalid Internal Payroll admin filters that blocked Django deployment checks.
- Added missing model-state migrations required by the release migration-drift gate.
- Fixed Rental Manpower assignment queries and stable settlement snapshot fingerprints.
- Allowed system-finalized immutable documents to retain a null finalizing user.
- Corrected the production hostname to `ims.sescco.com` and made it an explicit environment setting.
- Added a complete production environment template and secure, non-overwriting secret generator for the confirmed `172.20.0.0/16` IMS network.

## Stock transfer upgrade

- Added first-class project and office inventory locations.
- Added New, Used and No value stock conditions with Lost as an audited transfer outcome.
- Added atomic project-to-project, project-to-office and office-to-project transfers.
- Added project closeout allocation, office inventory, transfer receipts and whole-transfer reversal.
- Added location and condition support to inventory, activity, filters and exports.

This release completes the seven planned build upgrades and is prepared for an
isolated production deployment at `ims.sescco.com` beside other Docker Compose
projects.

## Included

- project-specific stock identity and immutable inventory movements;
- complete storekeeper workspace and administrator controls;
- advanced date, field and activity filtering with saved views;
- exact filtered XLSX/CSV export and protected Excel imports;
- rootless Django container, PostgreSQL, internal Nginx gateway and health checks;
- unique `ims` services, networks and persistent volumes;
- loopback or shared-proxy deployment options;
- pre-deployment backups, checksum-verified restore and operational guides;
- JSON logging, request IDs, secure production settings and workbook hardening.

## Deployment target

Follow `docs/DEPLOYMENT_IMS_SESCCO.md`. Before traffic is enabled, complete every
item in `docs/RELEASE_CHECKLIST.md`, including the Docker/CI runtime test suite
and an isolated restore test.

## Payroll merge baseline

The repository is now frozen as the authoritative IMS base for the production Payroll merge.
Before applying company/tenant schema upgrades to a production copy, capture a read-only baseline:

```bash
python manage.py merge_baseline_report --output /tmp/ims-pre-merge-baseline.json
bash scripts/verify-merge-baseline.sh
```

The existing IMS user table, migration history, Docker Compose identity and named PostgreSQL volume
are intentionally preserved during the merge.

## Payroll merge — Upgrade 2 platform core

The merged platform now has additive company/tenant foundation models in `apps.core`: Company,
CompanySettings, immutable AuditEvent, and transaction-safe NumberSequence. The existing IMS
`accounts.User`, inventory/project tables, migration history, and Docker volume identities remain
unchanged. Company assignment is intentionally deferred to Upgrade 3, where authenticated
CompanyMembership records will be introduced and existing users will be backfilled safely.

## Payroll merge — Upgrade 4 Inventory tenant boundary

Existing IMS Inventory and Project records are now company-owned through additive migrations.
Inventory request authorization, querysets, stock/transfer services, imports/exports, saved views
and Django-admin visibility are scoped through the authenticated active `CompanyMembership`.
Legacy stock balances and immutable movement history are preserved. Run
`python manage.py merge_inventory_tenant_report --fail-on-errors` after migration to reconcile
cross-company relationships before continuing to the shared Project merge.

## Payroll merge — Upgrade 6 Internal Payroll backend

The production Internal Payroll domain is now installed inside the merged IMS Django project and uses the existing IMS `accounts.User`, shared `core.Company`, and company-scoped membership/capability model. Branches, departments, employees, attendance/overtime, salary structures, payroll runs/adjustments, salary payments, bank exports and WPS are available through the preserved `/api/internal/...` backend contract. Sensitive payment fields use the required stable `PAYROLL_FIELD_ENCRYPTION_KEY`. Run `python manage.py merge_internal_payroll_report --fail-on-errors` after migrations.

## Payroll merge — Upgrade 11 production infrastructure

The merged Inventory + Payroll platform now has a single explicit release pipeline. Migrations and static
collection no longer run on ordinary Gunicorn restarts; deploy/restore use `scripts/release-tasks.sh`
before promoting the web container. Backups bind to the stable Payroll encryption-key fingerprint and
restore refuses a mismatched key. Readiness now requires both PostgreSQL connectivity and zero unapplied
Django migrations. The existing `ims` Compose project and `ims_*` persistent volume identities remain
unchanged.

## Payroll merge — Upgrade 12 production freeze

The 12-step IMS + Payroll merge is complete. A rehearsal-only Compose boundary now restores production
backups into `ims_merge_rehearsal_*` resources, applies the full migration chain, runs every merged-domain
reconciliation command and the complete Django regression suite, and compares protected legacy IMS row counts plus SHA-256 fingerprints of every pre-existing protected
field before/after migration. The deployable source/configuration tree is frozen by
`merge/production-freeze.sha256`, and the final frozen deploy entrypoint rejects source drift before handing off to the unchanged production preflight/deploy pipeline.
