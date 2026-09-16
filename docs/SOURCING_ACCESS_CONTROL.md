# SESCCO MS 1.0.101 — Sourcing Access-Control Authority

Upgrade 1.0.101 enables the Sourcing Directory module only through explicit, persisted Access Profile permissions. Sourcing remains a reference-only domain: these grants do not create or imply Inventory, Payroll, Projects, Documents, Rental Manpower or Accounting authority.

## Permission keys

- `sourcing.vendors.view` — see Vendor Sourcing and, when implemented, Material Finder results.
- `sourcing.vendors.manage` — create/update Vendor Sourcing reference data. Requires `sourcing.vendors.view`.
- `sourcing.manpower.view` — see Manpower Sourcing and, when implemented, Workforce Finder results.
- `sourcing.manpower.manage` — create/update Manpower Sourcing reference data. Requires `sourcing.manpower.view`.
- `sourcing.masters.view` — see Sourcing-only Material and Trade masters.
- `sourcing.masters.manage` — maintain Sourcing-only Material and Trade masters. Requires `sourcing.masters.view`.
- `sourcing.export.execute` — permit exports from authorized Sourcing areas. A profile must also have at least one Sourcing view permission.

Company Owner is the only built-in profile that receives Sourcing permissions automatically. Inventory Manager, Storekeeper, Finance, Internal Payroll, Rental Manpower Officer, Rental Supervisor/Foreman, Access Administrator, Reviewer and Auditor receive no Sourcing authority unless an administrator assigns a custom Access Profile containing Sourcing permissions.

## User-management workflow

An Access Administrator creates a custom Access Profile in Administration → Access Profiles, selects only the required Sourcing view/edit permissions, then assigns that profile when creating or editing a user. Vendor Sourcing and Manpower Sourcing are independent: a Vendor Viewer can have no Manpower access, and a Manpower Editor can have no Vendor access.

The existing security-version mechanism revokes a user's stale authenticated session after an administrator changes the user's Access Profile. Direct routes enforce the same backend permissions used by module visibility; hiding a navigation item is never the authorization boundary.

## Module visibility

`Sourcing Directory` appears in the module switcher only when the active Company Membership has at least one persisted `sourcing.*` grant. Users without Sourcing authority receive HTTP 403 when directly requesting `/app/sourcing/`. The Sourcing shell renders only the Vendor, Manpower and Reference areas allowed by the effective Access Profile.

## Production boundary

Upgrade 1.0.101 changes the Accounts permission constraint and grants the new Sourcing permissions only to existing built-in Owner profiles. It does not change Sourcing quantities/rates, Inventory quantities, Payroll formulas or any operational supplier/worker relationship. The 1.0.99 Sourcing isolation checks remain mandatory.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.114.
