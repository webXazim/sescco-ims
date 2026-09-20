# Rental document v3 migration contract

This document freezes the production boundary before the Rental Manpower document system is changed.
It is intentionally a **no-schema / no-data-rewrite** upgrade.

## Why this freeze exists

The current Documents workspace can create supplier-specific timesheet statements, settlement statements,
Supplier Invoice Received records and payment advice. The existing supplier timesheet is stored as a
`rental_timesheet` document with a supplier-qualified source identity. It is already immutable and may have
been printed, delivered or acknowledged by a supplier.

The next document architecture must therefore be additive. Existing v2 documents are historical evidence and
must never be converted in place merely to obtain the new layout.

## Frozen authority

- Rental attendance authority is `RentalTimesheetPeriod` in **Locked** state.
- Regular attendance is stored per worker per calendar day in `RentalTimesheetEntry`.
- Overtime is stored as one monthly worker total in `RentalTimesheetOvertime`; there is no authoritative daily
  OT distribution in the current schema.
- Supplier settlement authority remains the approved-or-later `SupplierSettlement` snapshot and does not depend
  on whether a printable supplier pack has been generated.
- Final `BusinessDocument` rows remain immutable, fingerprinted historical snapshots rather than accounting
  ledgers.
- Existing v2 print and delivery links remain valid through the migration.

## Existing v2 supplier-timesheet identity

The public creation alias is `supplier_timesheet`. It currently resolves to stored type `rental_timesheet`,
variant `supplier_timesheet`, with source identity:

`rental_manpower.rentaltimesheetperiod:supplier:<SUPPLIER_CODE>`

That representation is legacy-compatible and must remain readable/printable after v3 is introduced.

## Target v3 boundary

The planned Supplier Monthly Timesheet Pack is scoped to exactly:

**one supplier + one project + one month + one locked timesheet revision**

One pack will contain supplier/project summary pages followed by worker monthly detail sections. It will remain
one immutable `BusinessDocument`; a worker-only print/export will be a derived view of the finalized pack, not a
separate authoritative document row.

The pack must not contain commercial rates or settlement values. Daily OT must not be synthesized because the
current payroll authority stores OT monthly. Financial values remain in the Supplier Settlement Statement.

## Migration stages after this freeze

1. Add the new stored document type and schema foundation without rewriting v2 rows.
2. Build the bounded supplier-pack snapshot aggregator.
3. Add worker-month and supplier-summary contracts with reconciliation tests.
4. Add the production print renderer and derived worker export.
5. Replace the generic normal-creation drawer with a type-first, lazy-loading generator.
6. Clean the Documents read model and keep project timesheet printing in the Project Timesheets workspace.
7. Reconcile settlement/invoice/payment presentation without changing financial authority.
8. Cut supplier delivery over to the new pack and complete scale/production certification.

Current staged status: **Upgrade 14/14 is complete and production-frozen.** The stored v3 type, immutable supplier/project/month snapshot, complete worker monthly sheets, supplier summary, A4 renderer, derived worker export, bounded type-first generator, cleaned Documents workspace, financial reconciliation, supplier delivery cutover, 250-worker scale certification, and final production reconciliation are all wired into release and Payroll E2E gates. The final reconciliation accepts both legacy v2 supplier-qualified Rental Timesheet documents and v3 Supplier Timesheet Packs while validating v3 schema, source binding and source fingerprint. Normal generic Documents POST creation remains closed to v3; Project Timesheet remains in its operational workspace; historical v2 documents remain immutable/readable; and financial authority remains independent of whether a pack exists.

The machine-enforced form of this freeze is `merge/payroll-document-v3-freeze.json` and
`scripts/verify-payroll-document-v3-freeze.py`.


The final machine-enforced production freeze is `merge/payroll-document-v3-production-freeze.json` and `scripts/verify-payroll-document-v3-production-freeze.py`.
