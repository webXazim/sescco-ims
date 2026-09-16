# SESCCO MS 1.0.106 — Material Finder

## Purpose

Material Finder is a read-side Sourcing Directory workflow. It answers: **which reference Vendors can supply this material, at what last-known quantity/rate, and how recently was that information verified?**

It is not procurement, receiving, inventory, accounting, or a live supplier portal. Finder rows are projections of existing `SourcingVendorOffer` records only.

## Access authority

- `sourcing.vendors.view` is required to open Material Finder.
- `sourcing.vendors.manage` is required before an Edit reference action is rendered or the existing Vendor Supply Catalog mutation endpoints can be used.
- `sourcing.masters.view` is not required to search the Finder. A Vendor viewer may search controlled Material names/aliases without receiving Material Master authority.
- Company scope remains mandatory for every query.

## Included Vendor offers

Material Finder only returns active offer rows whose:

- Vendor is Active;
- Vendor is not Archived;
- Vendor is not in Trash; and
- Material is Active.

Inactive/Archived/Trash Vendors and inactive Materials remain preserved as history but are excluded from the on-demand sourcing result set.

## Search and filters

Search covers Material code/name/controlled aliases, specification, brand/model, and Vendor code/name/display name.

Filters include:

- availability;
- freshness;
- Material category;
- Vendor name/code;
- Vendor city/region;
- minimum/maximum reference rate; and
- deterministic server-side sorting/pagination at 25, 50, or 100 rows.

## Freshness policy

Freshness uses the company `SourcingSettings` policy. Defaults are:

- **Fresh:** verified within 7 days;
- **Needs verification:** older than the fresh window but not older than 30 days;
- **Stale:** older than 30 days; and
- **Never verified:** no verification timestamp exists.

The Finder shows age and quote-expiry cues, but it never changes offer data merely because it is old.

## Isolation guarantee

Material Finder does not:

- alter Inventory on-hand;
- create an Inventory Supplier or item;
- create a purchase/receiving transaction;
- create an Accounting posting;
- change Payroll or Rental Manpower; or
- write a sourcing verification event merely by searching.

The result is reference intelligence only. Staff must call/confirm the Vendor before relying on old quantity/rate information.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.116.
