# Inventory Manager Permission Reconciliation Hotfix — 1.0.116

The production reconciliation report showed one and only one built-in profile drift: system profile `role-inventory-manager` was missing `inventory.import.execute`.

The current authoritative role catalog already declares `Capability.IMPORT_INVENTORY` for Inventory Manager, so `permissions_for_legacy_role("inventory-manager")` expects this grant. The drift originates from the original `accounts.0005_granular_access_authority` backfill, where the Inventory Manager profile was created from Inventory view/edit/manage sets but omitted the import grant.

1.0.116 adds forward data migration `accounts.0014_inventory_manager_import_permission`. It adds exactly `inventory.import.execute` to active system Inventory Manager profiles when missing. It does not modify Storekeeper, custom profiles, memberships, scope rows, Inventory quantities, Payroll formulas, or the permission catalog.

The migration is database-alias aware and idempotent. Do not manually edit `accounts_access_profile_permission` and do not fake the migration. After deployment, `python manage.py merge_access_report --fail-on-errors` must complete successfully with an empty `system_profile_permission_drift` list.
