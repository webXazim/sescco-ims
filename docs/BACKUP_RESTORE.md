# Backup and restore

A complete IMS backup contains both PostgreSQL data and private invoice/import
attachments.

## Create a backup

```bash
./scripts/backup.sh
```

Each backup directory contains:

- `database.dump` — PostgreSQL custom-format dump;
- `media.tar.gz` — private media volume;
- `manifest.txt` — service and timestamp information;
- `SHA256SUMS` — integrity checksums.

The default location is `./backups/<UTC timestamp>/`. Default retention is 30
days and can be changed with `IMS_BACKUP_RETENTION_DAYS` in the shell or cron.

## Daily cron example

```cron
20 2 * * * cd /opt/inventory-management-system && ./scripts/backup.sh >> /var/log/ims-backup.log 2>&1
```

Copy backups to a second machine or private object storage. A backup that only
exists on the same VPS is not sufficient disaster recovery.

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
6. starts IMS and waits for health checks.

Set `IMS_SKIP_SAFETY_BACKUP=1` only when the current database is known to be
unrecoverable and storage space is insufficient.

Test restoration periodically on a separate server or isolated Compose project.
