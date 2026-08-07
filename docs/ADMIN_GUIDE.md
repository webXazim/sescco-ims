# Administrator guide

The administrator can use both the custom workspace and Django admin.

## Accounts

Create users in Django admin. Choose the Storekeeper role for operational users;
only administrators receive staff access. Deactivate accounts when access is no
longer required instead of deleting historical users.

## Corrections

Completed movements are read-only. Use the protected reversal action, supply a
clear reason, and confirm the resulting balance.

## Imports

Use the custom Imports area for the legacy catalog or opening-stock template.
Always review the dry-run rows, duplicate warnings and project assignment before
confirmation. Import confirmation is atomic.

## Backups

Run `./scripts/backup.sh` before manual maintenance and ensure a daily scheduled
backup exists. Test `./scripts/restore.sh` on an isolated environment.
