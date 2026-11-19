# Backup and restore

A complete merged-platform backup contains PostgreSQL data, private media,
the committed source-code history, and a recovery copy of the production
environment configuration. The configuration archive is permission-restricted
locally and encrypted when copied through the documented off-site rclone remote.
Payroll banking/payment fields inside PostgreSQL are encrypted with `PAYROLL_FIELD_ENCRYPTION_KEY`.

## Create a backup

```bash
./scripts/backup.sh
```

Each backup directory contains:

- `database.dump` — PostgreSQL custom-format dump;
- `media.tar.gz` — private media volume;
- `pulse-private.tar.gz` — private Project Pulse expense evidence;
- `source.bundle` — Git bundle containing the deployed source-code history;
- `production-config.tar.gz` — production environment configuration for
  recovery; protect the backup directory accordingly;
- `manifest.txt` — service, source revision, version, and Payroll encryption-key fingerprint;
- `SHA256SUMS` — integrity checksums.

## Production policy and current audit

The repository supplies the backup tooling; it does not prove that the VPS timer,
Drive credentials, monitoring or restore drills are configured. Inspect those on
VPS before treating this policy as operational. See [production setup](PRODUCTION_BACKUPS.md)
for the complete installation, capacity planning, monitoring and recovery runbook.

The default location is `./backups/<UTC timestamp>/`. Local retention reads the
shell first, then `.env.production`: `IMS_BACKUP_RETENTION_DAYS=7` and
`IMS_BACKUP_KEEP_COUNT=7`. Cleanup removes only completed IMS snapshots older
than seven days and always preserves the seven newest. Deployment/safety backups
also count; this is a minimum count plus an age policy, not a disk quota.
`IMS_BACKUP_RETENTION_DAYS=0` disables local cleanup.

New backups are created with a private umask in a hidden temporary directory,
verified, then renamed to the final timestamp. A failed capture removes its partial
directory and does not prune older snapshots. Local capture and off-site jobs each
have a non-blocking `flock` lock. Failed uploads retain the completed local backup;
the next scheduled job creates and uploads a fresh one. Failed older uploads are
not automatically retried: rerun `rclone copy` and `cryptcheck` for a chosen local
snapshot if its particular recovery point is needed.

Backups contain plaintext production credentials locally. File permissions protect
access; gzip is not encryption. The Drive destination must be an rclone `crypt`
remote wrapping a dedicated Google Drive backup folder. The script checks its type
before upload, uses `copy`, verifies with `cryptcheck`, and prunes only whole
UTC-timestamp folders older than `IMS_OFFSITE_BACKUP_RETENTION_DAYS=90` after the
new upload verifies. Setting remote retention to `0` disables remote cleanup.
Never point the crypt remote at a folder holding unrelated data.

For database/document consistency set `IMS_BACKUP_QUIESCE_WEB=1` (the production
example). This gracefully stops a running `ims_web` during DB/media/evidence
capture and restarts it before verification/upload. Expect a brief maintenance
outage; measure it on staging. Cleanup attempts restart on errors and SIGTERM.
The gateway remains running. Stop any additional external writers too. With `0`
(the script's compatibility default), PostgreSQL has a consistent logical snapshot,
but concurrent file changes can produce missing or mismatched attachments. A hard
kill or host crash can still leave the web service stopped; check it after a failed run.

Use the supplied systemd timer, scheduled for 02:20 Asia/Riyadh with up to 20 minutes
of jitter. Remove the old local-only cron job when enabling it. Review logs with
`journalctl -u ims-backup.service -n 100 --no-pager`.

## Validation and rehearsal

Validate a backup and restore its database into a disposable container without replacing production data:

```bash
bash scripts/verify-backup.sh /absolute/path/to/backup --require-recovery-bundle --restore-database
```

Run the complete isolated restore rehearsal before enabling the timer and at
least monthly afterwards:

```bash
./scripts/rehearse-production-freeze.sh /absolute/path/to/backup
```


## Encryption-key recovery requirement

The manifest contains a SHA-256 **fingerprint** of `PAYROLL_FIELD_ENCRYPTION_KEY`.
The actual key is also inside the protected production configuration archive; protect
the entire recovery set as secret data.
Store the actual key separately in a protected password/secret manager and a disaster-recovery copy.
A database/media backup without that matching key is not a complete recovery set once encrypted Payroll
payment data exists.

`restore.sh` compares the configured key fingerprint with the backup manifest and refuses a mismatch.
For a legacy pre-Upgrade-11 backup with no fingerprint, use
`IMS_ALLOW_LEGACY_BACKUP_WITHOUT_KEY_FINGERPRINT=1` only after confirming that backup predates encrypted
Payroll data.

## Restore

```bash
./scripts/restore.sh backups/20260807T020000Z --confirm
```

The restore script:

1. verifies checksums;
2. creates a safety backup of current IMS data;
3. stops only the IMS web and gateway services;
4. replaces only the IMS database;
5. replaces the IMS private-media and Project Pulse evidence volumes;
6. applies the current release migrations and merge-integrity checks;
7. collects static assets;
8. starts the merged web/gateway services and waits for health checks.

Set `IMS_SKIP_SAFETY_BACKUP=1` only when the current database is known to be
unrecoverable and storage space is insufficient.

Test restoration periodically on a separate server or isolated Compose project.
