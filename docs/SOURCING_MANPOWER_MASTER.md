# Sourcing Manpower Supplier Master — 1.0.106

## Purpose

The **Manpower Suppliers** directory is an independent Sourcing reference register. It answers **who SESCCO can call when manpower is needed**. It does not represent an engaged Rental Payroll supplier and does not create workers, assignments, timesheets, settlements, payroll, WPS or accounting entries.

`SourcingManpowerSupplier` remains deliberately separate from `rental_manpower.ManpowerSupplier`. Upgrade 1.0.105 added only `SourcingManpowerContact`, a company-scoped child record for the people SESCCO can call at that reference supplier.

## Directory

The supplier list is server driven from the first production release. Search covers supplier code/name, primary contact, saved contacts, phone/mobile, email, city/region, CR and VAT. Status views are Active, Inactive, Archived, Trash and All current. Pagination is bounded to 25, 50 or 100 records and the table exposes the number of active Sourcing workforce types without loading worker or payroll data.

## Supplier profile

The profile contains Overview, Workforce, Contacts and Activity tabs. Overview stores reference identity, primary contact summary, commercial identifiers, location, notes and lifecycle. Contacts are independent child records with a single active primary contact at a time; contacts are deactivated rather than destructively erased by normal application actions.

The Manpower Supplier master was certified independently in 1.0.105. Upgrade 1.0.106 now activates its sourcing-only Workforce Catalog while preserving the same separation from Rental Payroll. Trade/quantity/rate catalog authority is documented in `SOURCING_TRADE_WORKFORCE_CATALOG.md`.

## Lifecycle

A current supplier can move between Active and Inactive. Archive is reversible and removes a supplier from normal working lists without deleting reference evidence. Trash is a reversible 30-day retention state and requires the operator to type the exact supplier code plus a reason. Normal application routes do not hard-delete the supplier.

Every create/update/status/archive/trash/contact mutation writes immutable `AuditArea.SOURCING` evidence.

## Authorization

- `sourcing.manpower.view` is required for the directory and profile.
- `sourcing.manpower.manage` is required for create/edit/lifecycle/contact mutations.
- Vendor Sourcing, Inventory, Rental Payroll, Finance, Foreman and Storekeeper authority do not imply Manpower Sourcing access.
- Direct routes enforce the same backend permissions as the visible controls.

## Isolation

There is no foreign key, synchronization hook or write path from this master to Inventory, Projects, Internal Payroll, Rental Manpower, Documents or Accounting. A company may appear in both Sourcing and Rental Payroll, but the records are intentionally independent because one means **potential source to call** and the other means **operational supplier actually being used**.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.112.
