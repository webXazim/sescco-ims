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
