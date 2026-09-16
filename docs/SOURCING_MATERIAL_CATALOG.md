# SESCCO MS 1.0.102 — Material Master & Vendor Supply Catalog

Upgrade 1.0.102 activates the material/capability portion of the independent Sourcing Directory. It is **reference-only sourcing intelligence**. Nothing in this upgrade creates Inventory stock, purchase orders, payables, Accounting postings, Rental workers or Payroll records.

## Material Master

`SourcingMaterial` is the controlled vocabulary used when staff record what a Vendor says it can supply. Each material has a company-unique code/name, category, default unit, optional aliases, notes and Active/Inactive state. Aliases are normalized for search, and exact company-local name/alias collisions are rejected so terms such as “Steel Bar” do not silently represent multiple Sourcing Materials.

Material authority is separate from Vendor authority:

- `sourcing.masters.view` — list/search Sourcing Materials.
- `sourcing.masters.manage` — create, edit, activate and deactivate them.

A Sourcing Material is **not** an Inventory item and has no stock balance.

## Vendor Supply Catalog

A Vendor profile now has a live Supply Catalog. Each row records the Vendor's last-known capability for one controlled Sourcing Material:

- specification, brand and model;
- available quantity (nullable/unknown) and unit;
- minimum order quantity;
- availability: Available / Limited / Unavailable / Unknown;
- reference rate (nullable/unknown), currency and rate-valid-until date;
- lead time;
- last verified timestamp/user and verification note;
- free-form reference notes and Active/Inactive state.

Vendor Catalog read/write follows the existing Vendor permissions:

- `sourcing.vendors.view` — see Vendor Supply Catalog rows.
- `sourcing.vendors.manage` — add/edit/activate/deactivate rows.

A Vendor Editor does not automatically gain Material Master edit authority. It may select existing active Sourcing Materials; creating or changing master vocabulary requires the separate Master permission.

## Verification and history

When an editor marks an offer **Verified now**, the offer receives the current verification timestamp/user and the Vendor's `last_verified_at` is advanced. Every create, edit, activate or deactivate operation also writes immutable `SourcingVendorOfferRevision` evidence with before/after values. Contact name and verification note are retained with the revision where supplied.

The dedicated fast verification/history experience was activated in 1.0.104; the immutable evidence introduced with the catalog remains preserved.

## Isolation contract

The following are intentionally different concepts:

- Vendor available quantity ≠ SESCCO Inventory quantity.
- Vendor reference rate ≠ purchase cost or Accounting value.
- Sourcing Material ≠ Inventory Item.

There are no Sourcing foreign keys into Inventory, Payroll, Rental Manpower or Accounting. Historical operational records are never rewritten by Sourcing changes.

## Production checks

Run:

```bash
python3 scripts/verify-sourcing-domain-foundation.py
python3 scripts/verify-sourcing-access-control.py
python3 scripts/verify-sourcing-vendor-master.py
python3 scripts/verify-sourcing-material-catalog.py
python manage.py test apps.sourcing.tests.test_material_catalog --noinput
```

The Django runtime test remains part of the production release runner and migration rehearsal.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.111.
