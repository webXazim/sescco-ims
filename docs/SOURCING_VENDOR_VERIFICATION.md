# SESCCO MS 1.0.106 — Vendor Verification & History UX

## Purpose

Vendor Verification is the fast confirmation workflow for reference-only Vendor Supply Catalog rows. It is designed for the common sourcing call: SESCCO asks a Vendor what is available now, at what rate, under what lead time/conditions, then records that answer without opening the full catalog edit form.

## Authority

- `sourcing.vendors.view` can read Verification History.
- `sourcing.vendors.manage` is required to open or submit **Verify now**.
- Material Master authority is not required for verification because verification cannot change the controlled Material identity.
- Company scope is enforced for the Vendor, offer and every revision query.

## Quick verification fields

Quick verification may change only the current reference availability fields:

- availability;
- available quantity;
- unit;
- minimum order quantity;
- reference rate and currency;
- rate validity date;
- lead time;
- who SESCCO spoke with; and
- verification note.

It cannot change Material identity, specification, brand/model, Vendor identity, record lifecycle state or general offer notes. Those remain in the full Supply Catalog edit authority.

## Immutable evidence

Every successful verification:

1. locks the current Vendor/offer row;
2. captures the complete `before` sourcing snapshot;
3. writes the new current reference values;
4. stamps `last_verified_at` and `verified_by`;
5. advances the Vendor's latest verification timestamp;
6. appends one immutable `SourcingVendorOfferRevision` containing before/after, actor, contacted person and note; and
7. writes `sourcing.vendor_offer.verified` to the Sourcing audit ledger.

A confirmation is evidence even when quantity/rate did not change, so a new immutable revision is still recorded.

## History UX

Verification History is server-paginated at 25/50/100 rows. It shows:

- verification date/time;
- SESCCO user who recorded it;
- contacted Vendor person;
- verification note; and
- field-level before → after differences for availability, quantity, unit, minimum quantity, rate, currency, validity and lead time.

View-only users can inspect this evidence but cannot mutate it.

## Isolation guarantee

Verification updates only Sourcing reference tables and the Sourcing audit ledger. It never creates or updates:

- Inventory stock/on-hand;
- Inventory Supplier records;
- purchase/receiving transactions;
- Accounting payables/postings;
- Payroll or Rental Manpower records; or
- Projects/assignments.

Material Finder freshness is derived from the new verification timestamp, so a newly confirmed stale row becomes Fresh without any operational side effect.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.114.
