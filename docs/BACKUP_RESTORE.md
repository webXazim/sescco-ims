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
- `source.bundle` — Git bundle containing the deployed source-code history;
- `production-config.tar.gz` — production environment configuration for
  recovery; protect the backup directory accordingly;
- `manifest.txt` — service, source revision, version, and Payroll encryption-key fingerprint;
- `SHA256SUMS` — integrity checksums.

The default location is `./backups/<UTC timestamp>/`. Default retention is 30
days and can be changed with `IMS_BACKUP_RETENTION_DAYS` in the shell or cron.

## Daily cron example

```cron
20 2 * * * cd /opt/inventory-management-system && ./scripts/backup.sh >> /var/log/ims-backup.log 2>&1
```

Copy backups to a second machine or private object storage. A backup that only
exists on the same VPS is not sufficient disaster recovery.

## Verified encrypted Google Drive backups

Configure an encrypted rclone remote outside the repository, then set these
values in `.env.production`:

```dotenv
IMS_OFFSITE_RCLONE_CONFIG=/opt/sites/ims/.secrets/rclone.conf
IMS_OFFSITE_RCLONE_REMOTE=ms-backups:
IMS_BACKUP_RETENTION_DAYS=30
IMS_OFFSITE_BACKUP_RETENTION_DAYS=90
```

`scripts/backup-to-google-drive.sh` creates a complete recovery backup,
verifies its checksums plus database/media/source/configuration archives,
uploads it with `rclone copy` (never `sync`), then uses `rclone cryptcheck` to
verify the encrypted off-site copy. It only prunes files older than the explicit
off-site retention period after the new copy has passed verification.

Install the supplied daily systemd timer after the first manual upload and
rehearsal pass:

```bash
sudo install -m 644 deploy/systemd/ims-backup.service /etc/systemd/system/ims-backup.service
sudo install -m 644 deploy/systemd/ims-backup.timer /etc/systemd/system/ims-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ims-backup.timer
systemctl list-timers ims-backup.timer
```

Use `journalctl -u ims-backup.service -n 100 --no-pager` to review the most
recent backup run. Never put the rclone configuration, crypt password/salt, or
unencrypted `.env.production` in the repository.

## Validation and rehearsal

Validate a backup without replacing production data:

```bash
./scripts/verify-backup.sh /absolute/path/to/backup --require-recovery-bundle
```

Run the complete isolated restore rehearsal before enabling the timer and at
least monthly afterwards:

```bash
./scripts/rehearse-production-freeze.sh /absolute/path/to/backup
```


## Encryption-key recovery requirement

The backup contains a SHA-256 **fingerprint** of `PAYROLL_FIELD_ENCRYPTION_KEY`, never the key itself.
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
5. replaces only the IMS private-media volume;
6. applies the current release migrations and merge-integrity checks;
7. collects static assets;
8. starts the merged web/gateway services and waits for health checks.

Set `IMS_SKIP_SAFETY_BACKUP=1` only when the current database is known to be
unrecoverable and storage space is insufficient.

Test restoration periodically on a separate server or isolated Compose project.
