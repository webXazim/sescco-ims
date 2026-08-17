# Project Inventory

Private Django inventory management system for a contracting company. The
custom responsive workspace is the main product for storekeepers; Django admin
is reserved for administrator accounts and protected corrections.

## Production release

This package completes **all 7 planned upgrades** and is release `1.0.0`.

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
- isolated production deployment at `ims.a2tdev.com` beside other Docker projects;
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
- Stock activity: `http://127.0.0.1:8000/app/activity/`
- Stock transfers: `http://127.0.0.1:8000/app/transfers/`
- Office inventory: `http://127.0.0.1:8000/app/office/`
- Imports: `http://127.0.0.1:8000/app/imports/`
- Administrator: `http://127.0.0.1:8000/admin/`

Create operational users in Django admin with `role=Storekeeper`. Their staff
status remains disabled automatically.

## Production deployment for ims.a2tdev.com

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# Replace every placeholder secret and password.
./scripts/deploy-production.sh
./scripts/create-admin.sh
```

Docker publishes only `127.0.0.1:8087`. Route `ims.a2tdev.com` through the
existing host reverse proxy using `deploy/host-nginx/ims.a2tdev.com.conf`.

The Compose project, services, networks and volumes all use an `ims` prefix, so
this release can run beside another project without name or public-port
collisions. Deployment scripts never run global Docker cleanup and never remove
volumes.

See:

- `docs/DEPLOYMENT_IMS_A2TDEV.md`
- `docs/BACKUP_RESTORE.md`
- `docs/OPERATIONS.md`
- `docs/SECURITY.md`
- `docs/STOREKEEPER_GUIDE.md`
- `docs/ADMIN_GUIDE.md`
- `docs/RELEASE_CHECKLIST.md`

## Backups

```bash
./scripts/backup.sh
./scripts/restore.sh backups/<UTC-timestamp> --confirm
```

A complete backup contains the PostgreSQL custom-format dump, private media,
manifest and SHA-256 checksums. The restore script affects only IMS services and
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
are recorded in `docs/VALIDATION.md`.

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
