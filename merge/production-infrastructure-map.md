# Production infrastructure merge map

Upgrade 11 preserves the current IMS production identity and turns it into the deployment authority for
both Inventory and Payroll.

| Concern | Authority after Upgrade 11 |
| --- | --- |
| Compose project | `ims` |
| Database | existing IMS PostgreSQL database |
| Database volume | `ims_postgres_data` |
| Static volume | `ims_static_data` |
| Private media volume | `ims_media_data` |
| Release migration runner | `scripts/release-tasks.sh` |
| Production deploy | `scripts/deploy-production.sh` |
| Backup | `scripts/backup.sh` |
| Restore | `scripts/restore.sh` |
| Gateway | `nginx/default.conf` |
| Django runtime | Gunicorn, `config.wsgi:application` |
| Sensitive Payroll key | `PAYROLL_FIELD_ENCRYPTION_KEY` |

The database is never published to a host port. The Docker gateway remains loopback-bound and public TLS
continues to terminate at the host reverse proxy. `RUN_STARTUP_TASKS=0` is the normal runtime contract;
schema/static preparation is an explicit release action rather than a side effect of restarting Gunicorn.
