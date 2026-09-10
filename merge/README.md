# IMS + Payroll production merge

This repository is the authoritative merge target. The existing IMS project, database identity,
Docker Compose project name, PostgreSQL volume names, user table, and migration history are the
production baseline. Payroll is being merged into this codebase incrementally rather than mounted
as a second Django project.

## Frozen invariants

Until a dedicated merge upgrade explicitly changes one of these items, do not alter them:

- `AUTH_USER_MODEL = "accounts.User"` remains the existing IMS user model and integer primary key.
- Existing IMS migrations are immutable. New schema changes must be additive migrations.
- Docker Compose project name remains `ims`.
- PostgreSQL volume remains `ims_postgres_data`.
- Static/media volumes remain `ims_static_data` and `ims_media_data`.
- `apps.projects.Project` is the future cross-module project authority.
- Material suppliers and manpower suppliers remain separate business concepts.
- Payroll's standalone UUID `accounts.User`, standalone `RentalProject`, and conflicting migration
  histories are source material only and must never be copied directly into this repository.
- The final platform uses one PostgreSQL database, one Django session/authentication layer, one
  company/business context, and module-level authorization.

## Merge source

The payroll implementation being merged is the final DocGen V2 production-freeze PRS source.
Exact source revisions and archive hashes are recorded in `source-manifest.json`.

## Upgrade sequence

1. ✅ Merge baseline and repository freeze
2. ✅ Unified platform core / company foundation
3. ✅ Unified users and access memberships
4. ✅ Inventory tenant migration
5. ✅ Canonical shared projects
6. ✅ Internal Payroll backend merge
7. ✅ Rental Manpower backend merge
8. ✅ Payroll documents / management / audit
9. ✅ URL, static and frontend integration
10. ✅ Unified application shell
11. ✅ Production infrastructure merge
12. ✅ Migration rehearsal, regression and production freeze

## Upgrade 3 access bridge

- Existing `accounts.User` rows and integer primary keys are preserved.
- `CompanyMembership` is now the company-scoped authorization authority for new merged modules.
- Existing superusers backfill as Company Owner; legacy Inventory administrators backfill as
  Operations Administrator; legacy storekeepers backfill as Storekeeper.
- Operations Administrator intentionally does **not** receive Payroll, approval or payment authority.
- Upgrade 4 has replaced legacy Inventory request authorization with active-company membership
  capabilities. `User.role` / `is_inventory_admin` remain compatibility properties only and are no
  longer authoritative for Inventory views or services.
- Authenticated requests now resolve `request.company` and `request.company_membership`; active
  company selection is stored in the session only after validating an active membership.

After applying Upgrade 3 migrations on a staging/production backup, run:

```bash
python manage.py merge_access_report --fail-on-errors
```

This verifies that every active user has active company access and every active company retains an
active owner before Upgrade 4 begins tenant-scoping Inventory data.

## Upgrade 4 Inventory tenant boundary

Inventory, Projects, data exchange and saved workspace preferences are now explicitly company
owned. Existing legacy rows are backfilled only through additive migrations after the initial
company/access migration, then company ownership becomes mandatory. Request/query/service/admin
paths use the authenticated active company rather than the old global Inventory role.

After applying Upgrade 4 migrations, run:

```bash
python manage.py merge_inventory_tenant_report --fail-on-errors
```

Upgrade 5 can now safely make `apps.projects.Project` the shared Inventory + Payroll project
authority without exposing one company's records to another.

## Upgrade 5 canonical shared Projects

`apps.projects.Project` is now the only project authority for the merged platform. Existing IMS
integer project primary keys and Inventory foreign keys remain unchanged. Every project also has an
immutable UUID `reference`, which is the public/API project identifier used by merged Payroll.

The shared project now carries Payroll-compatible manager, actual end-date and On Hold lifecycle
fields. Project creation/update/status/trash activity writes to the platform audit log, and Inventory
closeout stamps the actual end date from the closing stock-transfer date.

Do not create `rental_manpower.RentalProject` in Upgrade 7. A deploy-time Django system check fails
if that duplicate model is introduced. The exact PRS-to-merged field mapping is documented in
`merge/project-authority-map.md`.

After applying Upgrade 5 migrations, run:

```bash
python manage.py merge_shared_projects_report --fail-on-errors
```

Legacy projects that were already completed before Upgrade 5 without a recorded actual end date are
reported as warnings rather than assigned a fabricated historical date. Review those dates as real
business data when appropriate.

## Upgrade 6 Internal Payroll backend

`apps.internal_payroll` is installed inside the authoritative IMS Django project and uses the
existing `accounts.User`, `accounts.CompanyMembership`, `core.Company`, audit, numbering and
field-encryption services. The original `/api/internal/...` API contract is preserved.

Before production use, configure `PAYROLL_FIELD_ENCRYPTION_KEY` and after migrations run:

```bash
python manage.py merge_internal_payroll_report --fail-on-errors
```

## Upgrade 7 Rental Manpower backend

`apps.rental_manpower` is now installed in the same Django project and PostgreSQL database. It
uses the merged Company/Membership authorization layer and preserves the original
`/api/rental/...` API contract.

There is deliberately **no** `rental_manpower.RentalProject` model or `rental_project` table.
`WorkerAssignment`, `RentalTimesheetPeriod`, `RentalAdjustment`, and `SupplierSettlement` all
reference the canonical `projects.Project`. Existing Inventory integer project PKs remain the
database FK authority; Rental API payloads expose/accept the immutable UUID `Project.reference`
through `apps.rental_manpower.project_adapter`.

Shared project lifecycle rules now account for both modules: open rental assignments block project
completion/archive and block moving a project to Trash. Historical rental foreign keys use
`PROTECT`, so protected Payroll history cannot be physically deleted with a Project.

After applying Upgrade 7 migrations, run:

```bash
python manage.py merge_rental_manpower_report --fail-on-errors
```

## Upgrade 8 Payroll Documents, Management and Audit

`apps.documents` now stores immutable payroll/workforce document snapshots inside the same IMS
PostgreSQL database. It uses the merged Company, User/Membership, numbering and audit authorities;
it does not introduce another financial ledger. Internal/Rental source records are resolved through
company-scoped selectors before a final document can be created.

Management and Reports are read-only cross-payroll projections over the merged source ledgers and
`core.AuditEvent`; the original `/api/management/`, `/api/reports/`, `/api/settings/`, and
`/api/documents/` contracts are preserved at the platform root.

After applying Upgrade 8 migrations, run:

```bash
python manage.py merge_documents_management_report --fail-on-errors
```

See `merge/payroll-documents-management-map.md` for the source/authority mapping and document
immutability boundary.

## Upgrade 9 URL, static and Payroll frontend integration

The production-freeze DocGen V2 Payroll frontend is now installed inside this Django project at
`/app/payroll/`. Its JS/CSS assets are isolated under `static/payroll/`; the existing Inventory
`static/js/app.js` and `static/css/styles.css` remain separate and unchanged. Payroll calls the
already-merged platform-root APIs directly, so there is no second backend, database, authentication
session, or proxy boundary.

Payroll-only company roles reach `/app/payroll/` from the authenticated home redirect, while
Inventory-only roles are denied the Payroll shell. Upgrade 10 now supplies the shared Business/Area
switcher above both module-specific navigation systems.

Production preflight runs:

```bash
bash scripts/verify-payroll-frontend.sh
```

This validates the namespaced bundle, frozen frontend asset hashes, CSS import graph, and Payroll
workspace route. See `merge/payroll-frontend-integration-map.md` for the integration boundary.

## Upgrade 10 unified application shell

Inventory and Payroll now share the same platform-level Business and Area switchers. The active business
is the existing session-backed `core.Company` / `CompanyMembership`; the Area switch contains Inventory
and/or Payroll according to that membership's actual workspaces. Module-specific navigation remains below
that shared layer, so Inventory and Payroll can retain their purpose-built rendering systems without becoming
separate applications again.

Company switching preserves the current Area only when the destination company membership can open it;
otherwise the request returns through the unified home resolver. Object-detail URLs are intentionally not
carried between companies.

Production preflight runs:

```bash
bash scripts/verify-platform-shell.sh
```

See `merge/platform-shell-map.md` for the shell hierarchy and security boundary.


## Upgrade 11 production infrastructure

Inventory and Payroll now share the existing IMS production deployment authority. Compose/database/static/media
volume names remain unchanged. Normal web-container startup uses `RUN_STARTUP_TASKS=0`; deployments and restores
run `scripts/release-tasks.sh` explicitly to perform deployment checks, migrations, all merge reconciliation
commands, and `collectstatic` before the web container is promoted.

Backups now record a SHA-256 fingerprint of the stable `PAYROLL_FIELD_ENCRYPTION_KEY` without storing the key.
Restore refuses a mismatched key, and readiness refuses a release with unapplied migrations. Production preflight
runs `scripts/verify-production-infrastructure.sh`. See `docs/MERGE_UPGRADE_11.md` and
`merge/production-infrastructure-map.md`.


## Upgrade 12 migration rehearsal, regression and production freeze

The merge is now complete. Upgrade 12 adds an isolated Compose override whose PostgreSQL, static,
media and network identities are all `ims_merge_rehearsal_*`, so a production backup can be restored
and migrated without attaching any live `ims_*` volume. The rehearsal captures protected legacy IMS row counts and pre-existing field-data fingerprints before
migration, applies the complete merge migration chain, runs every reconciliation command,
deployment/schema checks, `collectstatic`, and the full Django test suite, then refuses the freeze if any
protected legacy row or pre-existing field value changed.

The final source tree is bound by `merge/production-freeze.sha256`. The final deployment wrapper verifies this manifest before handing off to the unchanged Upgrade 11
preflight/deployment pipeline and its earlier baseline/frontend/shell/infrastructure contracts. The final merge
state records `completed_upgrade: 12`, `merge_complete: true`, and no next merge upgrade.

Before first production cutover, restore a current production backup into the isolated rehearsal and run:

```bash
./scripts/rehearse-production-freeze.sh /absolute/path/to/backup
```

Keep the generated `rehearsal-evidence/<UTC timestamp>/` directory with the release evidence. See
`docs/MERGE_UPGRADE_12.md` and `merge/production-freeze-map.md`.
