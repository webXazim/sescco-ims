# Backup and restore

A complete merged-platform backup contains PostgreSQL data and private media attachments.
Payroll banking/payment fields inside PostgreSQL are encrypted with `PAYROLL_FIELD_ENCRYPTION_KEY`.

## Create a backup

```bash
./scripts/backup.sh
```

Each backup directory contains:

- `database.dump` — PostgreSQL custom-format dump;
- `media.tar.gz` — private media volume;
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
