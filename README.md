# SESCCO MS

Private Management System for SESCCO. Production runs in single-company mode while retaining company-scoped database boundaries for authorization and historical integrity.

# IMS + Payroll Operations Platform

Private Django operations platform combining Inventory Management and Payroll Management for a contracting company. The
custom responsive workspace is the main product for storekeepers; Django admin
is reserved for administrator accounts and protected corrections.

## Production release

Current packaged release: **SESCCO MS 1.0.47 — nullable-safe tenant reconciliation, working lifecycle Actions, PostgreSQL-safe recoverable parent cascades, and complete Payroll E2E seed/report/document verification**.

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
- Stock activity: `http://127.0.0.1:8000/app/activity/`
- Stock transfers: `http://127.0.0.1:8000/app/transfers/`
- Office inventory: `http://127.0.0.1:8000/app/office/`
- Imports: `http://127.0.0.1:8000/app/imports/`
- Administrator: `http://127.0.0.1:8000/admin/`

Create operational users in Django admin with `role=Storekeeper`. Their staff
status remains disabled automatically.

## Production deployment for ims.sescco.com

```bash
bash scripts/create-production-env.sh
# Review .env.production; required secrets are generated and its mode is 600.
# Before the first merged cutover, rehearse against a current backup:
./scripts/rehearse-production-freeze.sh /absolute/path/to/current-production-backup
./scripts/deploy-production.sh
./scripts/create-admin.sh
```

For a testing deployment, `--seed` creates deterministic **DEMO-only** Payroll fixtures for complete workflow testing, including Internal Payroll, Rental Manpower, reports, WPS/export/reconciliation, payments, generated business documents, transfer/rate-change scenarios, and temporary-stop/termination/archive/delete lifecycle examples:

```bash
./scripts/deploy-production.sh --seed
```

`--seed` is idempotent. It intentionally creates visible DEMO/RDEMO records. The command chooses a collision-safe historical month before non-DEMO employment for its finalized synthetic payroll; if that cannot be proven safe, the seed aborts instead of mixing real employees into DEMO payroll history. Use it only where those test records are wanted.

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
