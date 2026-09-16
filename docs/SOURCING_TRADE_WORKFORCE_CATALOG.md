# SESCCO MS 1.0.106 — Worker Trade Master & Workforce Catalog

## Purpose

This release activates the **worker-type / trade vocabulary** and the per-Manpower-Supplier **Workforce Catalog** inside the independent Sourcing Directory. It answers a reference question only: *which supplier says it can provide which kind of worker, how many, at what reference rate, and how quickly?*

It does **not** represent workers actually hired by SESCCO.

## Hard operational boundary

`SourcingTrade` and `SourcingWorkforceOffer` remain owned by the `sourcing` application. They do not reference Rental Manpower suppliers, Rental Workers, assignments, timesheets, settlements, Payroll runs, Inventory or Accounting.

Changing `available_quantity`, `rate`, `overtime_rate`, `rate_basis`, `mobilization_lead_time` or `work_location` therefore changes sourcing intelligence only. Historical operational records are unaffected.

## Worker Type / Trade master

The Reference Masters permission controls the Trade master independently from Manpower Supplier editing.

Each Trade supports:

- company-local code;
- canonical name;
- category;
- controlled search aliases;
- notes;
- Active / Inactive state.

Normalized aliases are stored for bounded server-side search. Exact company-local name/alias collisions are rejected so terms such as **AC Technician**, **A/C Technician**, and **Air Conditioning Technician** can resolve to one controlled record instead of fragmenting the catalog.

## Workforce Catalog

A Manpower Supplier can have one current reference row per Trade. Each row supports:

- Availability: Available / Limited / Unavailable / Unknown;
- nullable available worker quantity;
- nullable standard reference rate;
- SAR or another three-letter currency;
- Hour / Day / Month rate basis;
- optional overtime reference rate;
- optional rate-valid-until date;
- mobilization / lead time;
- work location / geographic coverage;
- verifier user/time;
- optional contacted-person and verification note evidence;
- remarks;
- Active / Inactive state.

Blank quantity or rate means **unknown**, not zero.

## Verification and evidence

When `Verified now` is selected, SESCCO records the current user and time on the Workforce Offer and advances the supplier's last-verified timestamp. Every create, edit, activation and deactivation appends an immutable `SourcingWorkforceOfferRevision` snapshot. The dedicated fast verification/history experience and cross-supplier Workforce Finder remain the next controlled upgrade.

## Permissions

- `sourcing.masters.view` — view Worker Types / Trades.
- `sourcing.masters.manage` — create/edit/activate/deactivate Trades.
- `sourcing.manpower.view` — view Manpower Supplier Workforce Catalog rows.
- `sourcing.manpower.manage` — create/edit/activate/deactivate Workforce Catalog rows.

A Manpower Editor can choose an existing active Trade without being allowed to edit the Trade master.

## Lifecycle

Trades and Workforce Catalog rows use **Active / Inactive** reference lifecycle. Existing inactive records remain historical evidence and are not destructively deleted by the application. Manpower Supplier Archive/Trash lifecycle remains unchanged from 1.0.105.

## Deployment gate

Production release tasks must run:

- `scripts/verify-sourcing-trade-workforce-catalog.py`
- `python manage.py test apps.sourcing.tests.test_trade_workforce_catalog --noinput`
- all inherited Sourcing, access-control, Payroll, lifecycle and freeze authorities.

The release is bound to exact predecessor SHA-256 `ab85b97e9fa9f60467799c6c158e950f0d8fb12d0ddb0a6eb493e69e4ab75e0f`.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.116.
