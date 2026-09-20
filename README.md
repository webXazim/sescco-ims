# SESCCO MS

Private Management System for SESCCO. Production runs in single-company mode while retaining company-scoped database boundaries for authorization and historical integrity.

# IMS + Payroll Operations Platform

Private Django operations platform combining Inventory Management, Payroll Management, company Administration, and an independently permissioned reference-only Sourcing Directory for a contracting company. The
custom responsive workspace is the main product for storekeepers; Django admin
is reserved for Django superusers and protected corrections.

## Production release

Current packaged release: **SESCCO MS 1.0.117 — Supplier Timesheet Pack v3 Production Freeze & Acceptance (Upgrade 14/14)**.

Previous deployment baseline retained for verification: **SESCCO MS 1.0.117 — Sourcing Static Manifest Deployment Hotfix**.

This repository is at **merge Upgrade 12 of 12 — production freeze**. Inventory and Payroll now share one Django project, PostgreSQL database, authentication/company context, project authority, shell, and production deployment stack. The planned merge is complete.

Core capabilities:

- projects and compact project tags across the system;
- stock identity by Project + normalized material + supplier + supplier phone;
- safe additions, usage, adjustments, opening stock and linked reversals;
- atomic project-to-project, project-to-office and office-to-project transfers;
- condition allocation for new, used, no-value and lost closeout quantities;
- immutable stock history, row locking, idempotency and negative-stock blocking;
- complete storekeeper dashboard and operational management screens;
- advanced server-side search across stock and activity;
- today, week, month, quarter, year and custom inclusive date ranges;
- saved filter views, sorting and selectable columns;
- exact XLSX/CSV exports of every filtered result, not only the current page;
- legacy workbook preview/import and atomic opening-stock import;
- protected XLSX/XLSM parsing with archive expansion and path safety limits;
- private authenticated attachments;
- unified Inventory + Payroll production deployment at `ims.sescco.com` beside other Docker projects;
- health checks, JSON logs, backups, restore controls and operator documentation.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/development.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open:

- Storekeeper workspace: `http://127.0.0.1:8000/app/`
- Inventory Explorer: `http://127.0.0.1:8000/app/inventory/`
- Payroll workspace: `http://127.0.0.1:8000/app/payroll/`
- Administration / Users: `http://127.0.0.1:8000/app/administration/`
- Sourcing Directory: `http://127.0.0.1:8000/app/sourcing/`
- Stock activity: `http://127.0.0.1:8000/app/activity/`
- Stock transfers: `http://127.0.0.1:8000/app/transfers/`
- Office inventory: `http://127.0.0.1:8000/app/office/`
- Imports: `http://127.0.0.1:8000/app/imports/`
- Administrator: `http://127.0.0.1:8000/admin/`

Django admin is reserved for real Django superusers. SESCCO application users are
authorized through company-scoped `CompanyMembership` + `AccessProfile`; ordinary
Access Administrators never receive Django staff access. Production User Management CRUD is available through the normal Administration module and remains enforced by the company-scoped backend authority.
Backend security/API contract: `docs/USER_MANAGEMENT_BACKEND.md`. UI contract: `docs/USER_MANAGEMENT_UI.md`.
Rental Supervisor / Foreman production scope contract: `docs/RENTAL_SUPERVISOR_ACCESS.md`.
Rental document v3 migration contract: `docs/PAYROLL_DOCUMENT_V3_MIGRATION.md`.
Supplier Timesheet Pack worker extracts are derived from the immutable finalized pack and do not create one document row per worker. Final v3 production freeze: the normal creation path is the bounded type-first generator; the supplier pack is the primary outbound timesheet; the document reconciliation command now validates both legacy supplier-qualified timesheets and v3 packs, including schema/source/fingerprint bindings; and release acceptance includes the 250-worker scale gate in rehearsal/benchmark environments. See `docs/SUPPLIER_TIMESHEET_PACK_PRODUCTION_FREEZE.md`. Rental Documents now uses the purpose-first creation flow: choose Supplier Timesheet, Settlement Statement, Supplier Invoice Received, or Payment Advice first, then lazily select only the eligible month/supplier/project/source. Project Timesheet stays in the Project Timesheets workspace. The Documents register is now grouped by those supplier-facing business families, defers large immutable snapshots while listing records, and loads only a bounded summary fragment for the on-screen preview; full snapshot integrity verification remains on authoritative full-detail/print/share paths. Financial documents are now explicitly reconciled to the approved Supplier Settlement and its Locked source-timesheet revision: Supplier Invoice Received matches the settlement net, Payment Advice allocations must equal the paid amount, and none of those financial authorities depends on generating a printable Supplier Timesheet Pack. Supplier delivery now treats the v3 Supplier Monthly Timesheet Pack as the primary outbound timesheet, freezes a supplier-facing delivery manifest and safe PDF filenames at issue time, keeps Settlement Statement and Payment Advice opt-in, keeps Supplier Invoice Received inbound-only, and records supplier acknowledgement strictly as evidence of receipt rather than approval.
Internal Payroll / Finance duty-separation contract: `docs/INTERNAL_FINANCE_PERMISSIONS.md`.
Cross-module authorization leak-closure contract: `docs/CROSS_MODULE_ACCESS_LEAK_CLOSURE.md`.
Credential/session revocation contract: `docs/CREDENTIAL_SESSION_REVOCATION.md`.
Access History and guarded recovery contract: `docs/ACCESS_HISTORY_RECOVERY.md`.
Sourcing Directory domain/isolation contract: `docs/SOURCING_DOMAIN_FOUNDATION.md`.
Sourcing permission and User Management contract: `docs/SOURCING_ACCESS_CONTROL.md`.
Vendor Sourcing Master contract: `docs/SOURCING_VENDOR_MASTER.md`.
Material Master & Vendor Supply Catalog contract: `docs/SOURCING_MATERIAL_CATALOG.md`.
Sourcing Material Finder contract: `docs/SOURCING_MATERIAL_FINDER.md`.
Sourcing Manpower Supplier Master contract: `docs/SOURCING_MANPOWER_MASTER.md`.
Sourcing Worker Trade & Workforce Catalog contract: `docs/SOURCING_TRADE_WORKFORCE_CATALOG.md`.
Sourcing scale hardening contract: `docs/SOURCING_SCALE_HARDENING.md`.
Sourcing security certification contract: `docs/SOURCING_SECURITY_CERTIFICATION.md`.
Final Sourcing browser E2E + production freeze contract: `docs/SOURCING_BROWSER_E2E.md`.

## Production deployment for ims.sescco.com

```bash
bash scripts/create-production-env.sh
# Review .env.production; required secrets are generated and its mode is 600.
# Before the first merged cutover, rehearse against a current backup:
./scripts/rehearse-production-freeze.sh /absolute/path/to/current-production-backup
./scripts/deploy-production.sh
./scripts/create-admin.sh
```

For a testing deployment, `--seed` creates deterministic **DEMO-only** Payroll fixtures for complete workflow testing, including Internal Payroll, Rental Manpower, reports, WPS/export/reconciliation, payments, generated business documents, transfer/rate-change scenarios, and temporary-stop/termination/archive/delete lifecycle examples. Optional scale profiles add high-cardinality history for load testing:

```bash
./scripts/deploy-production.sh --seed
./scripts/deploy-production.sh --seed --seed-profile realistic
./scripts/deploy-production.sh --seed --seed-profile benchmark
```

`functional` remains the default. `realistic` adds 250 Internal employees + 750 Rental workers across six historical months and also seeds bounded Sourcing reference fixtures. `benchmark` expands Payroll to 2,000 Internal employees + 5,000 Rental workers across 12 months and Sourcing to 10,000 Vendors, 2,000 Materials, 50,000 Vendor offers, 5,000 Manpower Suppliers, 250 Trades and 25,000 Workforce offers. Large profiles are restart-safe and namespaced. By default the Sourcing benchmark refuses mixed non-SDEMO masters; on a disposable/test installation use `--allow-mixed-scale-seed` explicitly. See `docs/PAYROLL_SCALE_SEED.md` and `docs/SOURCING_SCALE_HARDENING.md`.

After loading `realistic` or `benchmark`, measure the high-cardinality Payroll paths with the packaged query-budget report:

```bash
python manage.py payroll_performance_report --fail-on-query-budget
# Or pin a specific seeded month:
python manage.py payroll_performance_report --period 2026-07 --fail-on-query-budget
```

The report measures Internal Attendance context, Internal Payroll preflight, the largest Rental project timesheet context, and Rental settlement context. The default release guard is 40 SQL queries per measured Internal/Rental path; elapsed milliseconds are reported for environment comparison but are not treated as a portable pass/fail threshold.

Supplier Timesheet Pack v3 has a separate production-scale certification. It measures the real immutable pack builder, snapshot size, full-pack print context and one derived worker sheet from a Locked Rental timesheet source:

```bash
python manage.py supplier_timesheet_pack_scale_report --fail-on-limits
# Pin a known high-volume supplier/project/month when certifying a release:
python manage.py supplier_timesheet_pack_scale_report \
  --period 2026-07 \
  --project-code DEMO-SCALE-P-001 \
  --supplier-code DEMO-SCALE-SUP-001 \
  --min-workers 250 \
  --fail-on-limits
```

The release budgets are two SQL queries for the supplier-scoped snapshot aggregator, zero SQL queries while building full-pack/worker print contexts, and at most 8 MiB for the packaged 250-worker certification fixture. Elapsed milliseconds are reported for environment comparison but are not used as a portable pass/fail threshold. See `docs/SUPPLIER_TIMESHEET_PACK_SCALE_CERTIFICATION.md`.

For Sourcing benchmark certification:

```bash
python manage.py sourcing_scale_report --require-benchmark-volume --fail-on-limits
```

This measures bounded Vendor/Material/Manpower/Trade directories, Material Finder, Workforce Finder, profile catalogs and the 5,000-row import parser.

For the final live Chromium Sourcing certification after deploying the benchmark rehearsal image:

```bash
export IMS_SOURCING_BROWSER_PASSWORD='REDACTED'
python scripts/certify-sourcing-browser-e2e.py \
  --base-url https://<release-host> \
  --username <sourcing-benchmark-user> \
  --password-env IMS_SOURCING_BROWSER_PASSWORD
```

The benchmark user must have Vendor Sourcing edit and Manpower Sourcing edit authority. The runner uses only deterministic `SDEMO-*` fixtures, verifies both Finder workflows in Chromium, and writes `sourcing-browser-certification.json`.

The functional seed intentionally creates visible DEMO/RDEMO records and chooses a collision-safe historical month before non-DEMO employment for its finalized synthetic payroll; if that cannot be proven safe, the seed aborts instead of mixing real employees into DEMO payroll history. Use seeding only where test records are wanted.

Docker publishes only `127.0.0.1:8087`. Route `ims.sescco.com` through the
existing host reverse proxy using `deploy/host-nginx/ims.sescco.com.conf`.

The Compose project, services, networks and volumes all use an `ims` prefix, so
this release can run beside another project without name or public-port
collisions. Deployment scripts never run global Docker cleanup and never remove
volumes.

See:

- `docs/DEPLOYMENT_IMS_SESCCO.md`
- `docs/BACKUP_RESTORE.md`
- `docs/OPERATIONS.md`
- `docs/SECURITY.md`
- `docs/STOREKEEPER_GUIDE.md`
- `docs/ADMIN_GUIDE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/MERGE_UPGRADE_12.md`

## Backups

```bash
./scripts/backup.sh
./scripts/restore.sh backups/<UTC-timestamp> --confirm
```

A complete backup contains the PostgreSQL custom-format dump, private media, manifest and SHA-256 checksums. The manifest binds the backup to the Payroll field-encryption-key fingerprint; keep the actual encryption key separately in protected disaster-recovery storage. The restore script affects only IMS services and
volumes.

## Quality checks

```bash
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
ruff check .
coverage run manage.py test
coverage report
```

Static validation commands and the runtime limitation of this build environment
are recorded in `docs/VALIDATION.md`. The canonical `scripts/deploy-production.sh` entrypoint verifies `merge/production-freeze.sha256` before preflight, backup, release tasks and cutover. The compatibility `scripts/deploy-production-freeze.sh` wrapper remains available, but is no longer required for normal production deployment. Source/configuration drift from the packaged release blocks deployment.

## Inventory integrity rules

- Current quantity is never directly editable.
- Every balance change creates an immutable movement.
- Stock use and negative adjustments cannot create negative stock.
- Browser retries and double-clicks cannot repeat movements.
- Projects and units lock after the first movement.
- Closed or archived projects cannot receive stock activity.
- Stock records can be archived only at zero balance.
- Transfers create linked immutable outbound and inbound movements in one transaction.
- Lost transfer quantities never create destination stock; no-value stock carries zero value.
- A transfer reversal always reverses the complete transfer and requires destination stock.
- Completed movements are corrected through linked administrator reversals.
- Export and import actions retain user and filter provenance.
- Private uploads are served only through authenticated Django routes.

Never use `docker compose down -v` in production.

## Merged Payroll platform

The merged platform now includes the production Internal and Rental Payroll backends plus the DocGen V2 Payroll frontend. Inventory and Payroll share the authenticated Company context and the Upgrade 10 Business/Area switcher. Production deployments must configure a stable `PAYROLL_FIELD_ENCRYPTION_KEY`; see `docs/MERGE_UPGRADE_6.md` and `merge/platform-shell-map.md`.

### Benchmark seeding on an existing test company

`realistic` and `benchmark` remain demo-only by default. For an existing **disposable/test** company that already contains normal employee/worker masters, use the explicit guarded override:

```bash
./scripts/deploy-production.sh --seed --seed-profile benchmark --allow-mixed-scale-seed
```

The override only permits namespaced `DEMO-*` / `RDEMO-*` scale records and refuses the seed if a target scale month contains non-DEMO Internal attendance/payroll history.
.
