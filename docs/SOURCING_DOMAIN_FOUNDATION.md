# Sourcing Directory domain foundation — 1.0.99

SESCCO MS 1.0.99 introduces an **independent, reference-only Sourcing Directory domain**. The purpose is deliberately narrow: record who SESCCO may call and what that source last said it could provide. Sourcing is not Inventory, Procurement, Rental Payroll, Accounting, Projects, or an operational supplier authority.

## Frozen domain boundary

Sourcing records MUST NOT create, update, delete, post, assign, receive, issue, transfer, settle, pay or otherwise mutate operational records. In particular:

- `SourcingVendor` is not `inventory.Supplier`.
- `SourcingVendorOffer.available_quantity` is not stock-on-hand.
- `SourcingManpowerSupplier` is not `rental_manpower.ManpowerSupplier`.
- `SourcingWorkforceOffer.available_quantity` is not an actual Rental Worker count.
- Sourcing rates are reference quotations only; they are not purchase, settlement, payroll or accounting rates.
- An operational transaction must explicitly copy/snapshot any relevant sourcing information at the point of use. No automatic synchronization is allowed.

The Django system check `sourcing.E001/E002` rejects database relations from Sourcing into operational applications. The initial migration contains only `core`, `accounts`, and `sourcing` relations.

## Foundation schema

1.0.99 establishes company-scoped masters and reference offer/history tables:

- `SourcingVendor`
- `SourcingMaterial`
- `SourcingVendorOffer`
- immutable `SourcingVendorOfferRevision`
- `SourcingManpowerSupplier`
- `SourcingTrade`
- `SourcingWorkforceOffer`
- immutable `SourcingWorkforceOfferRevision`
- `SourcingSettings`

Material aliases and Trade aliases are stored as normalized search-reference aliases on their independent Sourcing masters. Offer quantities/rates are nullable so **Unknown** is represented honestly rather than as a fake zero.

## Verification history

The current offer row is optimized for Finder/search use. Verification revisions are append-only and retain before/after snapshots, actor/contact note, verification time and immutable source identifiers. Revision instance update/delete and queryset update/delete are rejected.

## Freshness

`SourcingSettings` defaults to:

- Fresh: 7 days
- Stale threshold: 30 days
- Currency: SAR

The actual Finder UI is implemented in later controlled upgrades; 1.0.99 stores only the policy foundation.

## Access state in 1.0.99

The Sourcing application and `/app/sourcing/` namespace are registered, but the module is intentionally **fail-closed for every normal membership**. `PlatformModule.SOURCING` exists so routing and shell identity are frozen, while `membership_can_module(..., SOURCING)` returns false until 1.0.101 introduces explicit Vendor/Manpower Sourcing permissions.

This prevents a schema-only foundation release from accidentally granting access through an existing Inventory, Rental, Finance, Storekeeper, Supervisor or Administration profile.

## Audit

`AuditArea.SOURCING` is now a first-class immutable platform audit namespace. Later CRUD/verification services must record Sourcing actions there rather than reusing Inventory or Rental audit areas.

## Deployment

This release contains migrations:

- `core.0006_sourcing_audit_area`
- `sourcing.0001_sourcing_domain_foundation`

Run the normal migration rehearsal before production mutation. No Payroll formula, Rental settlement formula, Inventory quantity formula or existing lifecycle behavior is changed by 1.0.99.

## 1.0.101 permission cutover

The 1.0.99 reference-only domain boundary remains unchanged in SESCCO MS 1.0.101. The module is no longer unconditionally hidden; it is exposed only when the active membership has explicit persisted `sourcing.*` Access Profile grants. No operational Inventory, Payroll, Rental Manpower, Project or Accounting relationship was added.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.115.
