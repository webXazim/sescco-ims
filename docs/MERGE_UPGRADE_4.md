# Merge Upgrade 4 — Inventory tenant migration

Upgrade 4 converts the existing IMS Inventory domain from legacy global ownership to the merged
platform's explicit company boundary. It is additive: existing user primary keys, stock balances,
movement history, migration history, Docker identity and PostgreSQL volume are preserved.

## Schema ownership

The following existing root records now belong to exactly one `core.Company`:

- `projects.Project`
- `inventory.Unit`
- `inventory.Supplier` (material supplier)
- `inventory.InventoryLocation`
- `inventory.StockItem`
- `inventory.StockDocument`
- `inventory.StockMovement`
- `inventory.StockTransfer`
- `data_exchange.ImportJob`
- `data_exchange.ExportAudit`
- `explorer.SavedView`
- `explorer.TablePreference`

Child records such as transfer lines and import rows inherit their tenant from their immutable
parent and are checked by the post-migration reconciliation command.

## Safe migration sequence

The four additive migrations are ordered after the Upgrade 3 company/access backfill:

1. `projects.0003_company_scope`
2. `inventory.0013_company_scope`
3. `data_exchange.0002_company_scope`
4. `explorer.0004_company_scope`

The migrations add nullable company keys, backfill legacy rows only when ownership can be
determined safely, then make ownership mandatory. Legacy global uniqueness is converted to
company-scoped uniqueness for project codes, units, material suppliers, inventory-location codes,
stock identities and idempotency keys.

A migration refuses to guess when the legacy database has an ambiguous multi-company state.

## Authorization and query boundary

Inventory requests now require an active `CompanyMembership` with Inventory workspace access.
Administrative Inventory operations require the appropriate membership capability. Normal
Inventory, Project, Import/Export and Explorer reads are scoped to `request.company`.

The legacy `accounts.User.role` and `is_inventory_admin` property remain only as compatibility
surface for old code outside the merged authorization path; they are no longer authoritative for
Inventory request access.

Service-layer stock and transfer operations independently verify both the actor's company access
and the company identity of referenced projects, units, locations and stock rows. Idempotent
movement/transfer retries are isolated per company.

Django-admin querysets for Projects, Inventory, Import/Export and Explorer records are scoped to
the active company. Saved views and table preferences are read-only in admin so they can only be
mutated through their company-aware workspace flow.

## Data-integrity checks

`python manage.py merge_inventory_tenant_report --fail-on-errors` verifies the merged Inventory
company graph, including:

- project/location ownership;
- stock location/project/unit ownership;
- document and movement ownership;
- movement reversals;
- transfer source/destination ownership;
- transfer-line stock ownership and source/destination location consistency;
- transfer-generated movement ownership;
- import project/unit ownership;
- saved-view and table-preference owner memberships.

Production deployment runs this command after Django migration/check steps.

## Staging / production rehearsal

Before applying Upgrade 4 to a restored production backup, keep the pre-merge baseline report
from Upgrade 1. After migration run:

```bash
python manage.py merge_access_report --fail-on-errors
python manage.py merge_inventory_tenant_report --fail-on-errors
python manage.py makemigrations --check --dry-run
python manage.py check --deploy --fail-level ERROR
```

Compare the per-model totals in the tenant report with the Upgrade 1 baseline. Upgrade 4 must not
change stock quantities, historical movements or existing project/record counts except for new
company/membership metadata rows introduced by the merge.

## Deferred to Upgrade 5

`apps.projects.Project` is now tenant-safe but retains the existing IMS project schema. Upgrade 5
will extend it into the canonical cross-module Project authority before Rental Payroll is attached,
rather than creating or importing Payroll's standalone `RentalProject` model.
