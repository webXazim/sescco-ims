# IMS + Payroll Merge — Upgrade 2: Unified Platform Core

This upgrade adds the tenant/business primitives required by the merged Inventory + Payroll platform without assigning existing IMS data to a tenant yet.

## Added

- `core.Company` — UUID tenant/business authority.
- `core.CompanySettings` — validated timezone, currency, and country defaults.
- `core.NumberSequence` — transaction-safe company-scoped business numbering.
- `core.AuditEvent` — immutable cross-module audit ledger tied to the existing `accounts.User`.
- `CompanyOwnedModel` / `CompanyScopedQuerySet` for new merged-domain records.
- Company-aware timezone and logging context, inactive until Upgrade 3 resolves a user's active company.
- Production-safe audit IP extraction that only trusts forwarding headers from configured trusted proxies.

## Deliberately unchanged

- `AUTH_USER_MODEL` remains `accounts.User` with existing integer primary keys.
- No existing IMS inventory/project/data-exchange table has a company FK yet.
- No default company is guessed or auto-selected.
- Existing IMS migration files and Docker volume identities remain frozen.

Upgrade 3 introduces `CompanyMembership`, creates/backfills the initial company/memberships explicitly, and adds authenticated company context middleware.
