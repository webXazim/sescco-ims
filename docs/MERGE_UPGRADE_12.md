# Merge Upgrade 12 — Migration rehearsal, regression and production freeze

Upgrade 12 is the final planned IMS + Payroll merge upgrade. It does not introduce another business
module or replace any authority established by Upgrades 1–11. Its purpose is to prove that the merged
release can be applied to real IMS data safely and to freeze the exact deployable source tree.

## Final authorities

The production platform remains one Django application and one PostgreSQL database:

- authentication: existing `accounts.User`;
- business/tenant: `core.Company` + `accounts.CompanyMembership`;
- projects: `projects.Project`;
- Inventory: existing IMS Inventory models and history;
- Internal Payroll: `apps.internal_payroll`;
- Rental Manpower: `apps.rental_manpower`;
- Payroll documents: `apps.documents`;
- management/reports/settings: merged platform-root APIs;
- deployment identity: Compose project `ims` and existing `ims_*` persistent volumes.

No second Payroll database, user table, project authority, Django project, or authentication/session
boundary is introduced.

## Isolated rehearsal boundary

`docker-compose.rehearsal.yml` overrides every persistent/network identity used by the rehearsal:

- `ims_merge_rehearsal_postgres_data`;
- `ims_merge_rehearsal_static_data`;
- `ims_merge_rehearsal_media_data`;
- `ims_merge_rehearsal_edge`;
- `ims_merge_rehearsal_database`.

`scripts/rehearse-production-freeze.sh` resolves the Compose graph before touching data and aborts if
any production `ims_*` volume/network name remains. It resets only the rehearsal project and volumes.
The live IMS services are never stopped by the rehearsal.

## Rehearsal gate

Run the rehearsal against a current production backup before the first merged production cutover:

```bash
./scripts/rehearse-production-freeze.sh /absolute/path/to/backup
```

The runner performs, in order:

1. backup checksum and Payroll encryption-key fingerprint validation;
2. isolated Compose resource proof;
3. restore of PostgreSQL and private media into rehearsal-only volumes;
4. protected pre-migration IMS row-count snapshot plus SHA-256 fingerprints of every pre-existing field in protected legacy tables;
5. migration plan + full migration application + zero-pending-migration check;
6. company/access, Inventory, shared Projects, Internal Payroll, Rental Manpower, and
   Documents/Management reconciliation commands with `--fail-on-errors`;
7. `check --deploy`, schema-drift check, and `collectstatic`;
8. the full Django test suite;
9. protected post-migration row-count and legacy-field fingerprint comparison (new additive columns are excluded from the fingerprint contract);
10. SHA-256 checksums for the generated evidence directory.

The protected preservation set covers existing IMS users (including group/permission join tables), Projects,
Inventory master/history records, import/export audit rows, and Explorer saved preferences. Upgrade 12 records
the exact columns present before migration and hashes ordered row JSON over those columns; after migration it
rehashes only that same pre-migration column contract. This catches silent changes to legacy quantities,
identities, references, dates, notes, and other existing fields while allowing intentionally additive
company/payroll columns. New company/membership/payroll rows are not required to match pre-migration counts
because they are intentionally introduced by the merge.

Legacy pre-Payroll backups may not contain `payroll_field_key_fingerprint_sha256`. For a backup that is
confirmed to predate encrypted Payroll data, the rehearsal requires the same explicit one-time override as
restore: `IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT=1`. Never use that override for a backup that may
contain encrypted Payroll fields.

Set `IMS_REHEARSAL_KEEP=1` only when an operator intentionally wants to retain the isolated rehearsal
containers/volumes after the run for investigation. The default destroys those rehearsal resources on
success or failure while retaining the host-side evidence directory.

## Production freeze

`merge/production-freeze.sha256` hashes the deployable source/configuration surface (application code,
settings, templates, static assets, migration files, deployment scripts/configuration, merge contracts,
and release documentation). Runtime data, secrets, caches, backups, `.git`, and the freeze manifest
itself are excluded.

`scripts/deploy-production-freeze.sh` runs `scripts/verify-production-freeze.sh` before handing off to the
unchanged Upgrade 11 `scripts/deploy-production.sh` pipeline. This preserves the already-frozen Upgrade 11
infrastructure checksums while still blocking Upgrade 12 source/configuration drift before a container image
is built or a database is changed.

The Git working tree is also required to be clean. The hash freeze is an artifact-integrity boundary;
the clean-tree rule is the operator/repository-integrity boundary. Both must pass.

## Final cutover sequence

After a successful isolated rehearsal and evidence review:

```bash
./scripts/verify-production-freeze.sh
./scripts/deploy-production-freeze.sh
```

Upgrade 11's deployment ordering remains authoritative: preflight → build → database readiness → safety
backup → explicit release tasks/migrations/reconciliation/static collection → web promotion → gateway
promotion → live readiness/static smoke checks.

## Rollback and recovery

The deployment creates a pre-cutover database/media backup. Because merge migrations are additive and
follow expand → backfill → constrain, the previous release can remain available during the migration
preparation window. If recovery requires restoring data, use the documented `scripts/restore.sh` process
with the same long-lived `PAYROLL_FIELD_ENCRYPTION_KEY`; restore rejects a mismatched key fingerprint.

Do not edit historical merge migrations after this freeze. Future product work starts from this frozen
merged baseline with new additive migrations and a new release manifest rather than changing the Upgrade
12 artifact in place.
