# SESCCO MS 1.0.107 — Workforce Finder & Verification History

Workforce Finder is a reference-only Sourcing workflow. It answers **which Manpower Supplier can provide this worker type, in what quantity, at what last-known rate/basis, where, how quickly, and how recently that statement was verified**.

The finder is company-scoped and server-driven. It searches controlled Trade code/name/aliases/category plus Manpower Supplier identity, work-location coverage and mobilization text. Results support 25/50/100 pagination and filters for availability, freshness, category, supplier, location, rate basis and rate range. Inactive Trades, inactive Workforce rows, inactive/archived/trashed suppliers and other-company data are excluded.

Freshness uses the same Sourcing Settings policy as Material Finder: Fresh, Needs verification, Stale and Never verified. Rate-valid-until is shown separately so a fresh quantity confirmation cannot make an expired rate look current.

`Sourcing Manpower View` can use Finder and inspect immutable Verification History. `Sourcing Manpower Edit` additionally exposes **Verify now** and Edit actions. Quick verification can update only sourcing-owned availability, quantity, standard/overtime rate, currency, rate basis, validity, mobilization, work-location coverage and verification note. It stamps the confirming SESCCO user/time, records the contacted person when supplied, updates supplier freshness and appends a new immutable `SourcingWorkforceOfferRevision` even when the supplier confirms the same values.

This module has **no operational integration**. Workforce quantities are not Rental Workers; sourcing rates are not Payroll/settlement rates. Finder or verification never creates suppliers in Rental Manpower, workers, assignments, attendance, timesheets, settlements, Inventory records, purchase records or Accounting postings.

Production deployment must run `scripts/verify-sourcing-workforce-finder.py` plus `python manage.py test apps.sourcing.tests.test_workforce_finder --noinput` in the normal release rehearsal.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.115.
