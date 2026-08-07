# Administrator guide

The administrator can use both the custom workspace and Django admin.

Use the workspace links shown in Django admin for stock additions, usage,
adjustments, reversals and imports. Those workflows preserve balances and the
immutable movement history. Django admin is intended for account management,
project/unit setup, stock identity corrections and audit review.

## Accounts

Create users in Django admin. Choose the Storekeeper role for operational users;
only administrators receive staff access. Deactivate accounts when access is no
longer required instead of deleting historical users.

The account list includes safe bulk activate/deactivate actions. Deactivation
never includes the signed-in account or a superuser.

## Corrections

Completed movements are read-only. Use the protected reversal action, supply a
clear reason, and confirm the resulting balance.

Stock balances, latest purchase values, lifecycle status and movements are
read-only in Django admin. Use the buttons in each stock or movement record to
open the corresponding protected workspace operation.

## Imports

Use the custom Imports area for the legacy catalog or opening-stock template.
Always review the dry-run rows, duplicate warnings and project assignment before
confirmation. Import confirmation is atomic.

## Backups

Run `./scripts/backup.sh` before manual maintenance and ensure a daily scheduled
backup exists. Test `./scripts/restore.sh` on an isolated environment.
