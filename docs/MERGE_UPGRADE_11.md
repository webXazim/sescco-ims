# Merge Upgrade 11 — Production infrastructure

Upgrade 11 keeps the existing IMS deployment identity while hardening the merged Inventory + Payroll
platform for production operations.

## Frozen infrastructure identities

Do not rename these during the merge/final cutover:

- Compose project: `ims`
- PostgreSQL volume: `ims_postgres_data`
- Static volume: `ims_static_data`
- Media volume: `ims_media_data`
- Loopback gateway: `127.0.0.1:${IMS_HTTP_PORT:-8087}`

The PostgreSQL service remains isolated on the internal `ims_database` Docker network.

## Release ordering

`RUN_STARTUP_TASKS` now defaults to `0`. Normal Gunicorn container restarts do not run migrations or
`collectstatic`.

`scripts/deploy-production.sh` performs the release in this order:

1. immutable merge/frontend/shell/infrastructure preflight;
2. build the new web image;
3. start/wait for PostgreSQL;
4. create a pre-deployment PostgreSQL + media backup;
5. run `scripts/release-tasks.sh` against the new image;
6. apply migrations and all merge reconciliation commands;
7. collect static files **without clearing previous release assets**;
8. replace the web container and wait for readiness;
9. update/wait for the gateway;
10. run live Django and static-asset smoke checks.

Keeping the previous hashed static assets during cutover means an old web response remains able to load
its assets while the new web container is being promoted. Old collected assets can be cleaned during a
separate maintenance window after the rollback window has expired.

All future schema work should continue the merge policy of expand → backfill → constrain. Do not make a
destructive migration that requires the old release to stop before the new release is ready unless a
planned maintenance deployment is being performed.

## Encrypted Payroll data and backups

`PAYROLL_FIELD_ENCRYPTION_KEY` is a long-lived data-encryption key, not a disposable deployment secret.
Changing it without a dedicated key-rotation migration makes encrypted salary-payment destinations
unreadable.

Every Upgrade 11 backup records only:

`payroll_field_key_fingerprint_sha256=<SHA-256 fingerprint>`

The key itself is never written into the backup archive. Keep the actual `.env.production` secret (or the
key alone) in an independent protected secret/password manager and disaster-recovery location.

Restore refuses to proceed when the configured key fingerprint differs from the backup fingerprint.
Legacy backups without a fingerprint require the explicit
`IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT=1` override and should only be restored after confirming
they predate encrypted Payroll data.

## Readiness

`/app/health/live/` confirms the Django process is alive.

`/app/health/ready/` confirms both:

- PostgreSQL is reachable;
- the running code has no unapplied Django migrations.

A release with pending migrations therefore cannot become healthy accidentally.

## Reverse proxy trust

Set `DJANGO_TRUSTED_PROXY_IPS` to the Docker gateway/proxy network visible to Django. The supplied example
includes Docker's common private bridge range, but production should tighten it to the actual `ims_edge`
subnet where practical.

## Web-container hardening

The Django container now runs with:

- non-root UID/GID;
- read-only root filesystem;
- all Linux capabilities dropped;
- bounded PID count;
- writable named volumes only for media/static plus a small `/tmp` tmpfs.

Private media remains unreachable through Nginx and is served only by authenticated Django views.
