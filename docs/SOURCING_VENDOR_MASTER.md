# SESCCO MS 1.0.101 — Vendor Sourcing Master

Upgrade 1.0.101 makes the Vendor half of the independent Sourcing Directory usable in production while preserving the Sourcing isolation authority introduced in 1.0.99 and the explicit Access Profile authority introduced in 1.0.100.

## Authority boundary

`SourcingVendor` is a reference company SESCCO may call when it needs material. It is not `inventory.Supplier`, does not own stock, does not create purchasing or payable records, and does not post to Payroll or Accounting. Sourcing data may later be copied/snapshotted into a real operational transaction, but this release performs no such integration.

All Vendor pages require `sourcing.vendors.view`. Create, edit, contact maintenance, status changes, Archive, Trash and restore require `sourcing.vendors.manage`. Existing Inventory, Storekeeper, Payroll, Foreman and Finance roles receive no implicit Vendor access.

## Vendor directory

`/app/sourcing/vendors/` uses server-side company-scoped search, status filters, deterministic sorting and bounded pagination. The default is 50 rows with 25/50/100 choices. Search covers Vendor code/name/display name, company official phone/email, primary contact name/mobile/email, full address fields (address, street number, district, city, region, postal code), CR/VAT and active contact-person identity fields. Trashed records are excluded from normal filters and have a dedicated Trash view.

The browser receives only the requested page; it does not preload the Vendor register. Optional table columns are hidden locally in the browser and do not change backend authority.

## Vendor profile and contacts

The Vendor master is now deliberately split into three UI sections: **Vendor Identity**, **Primary Contact**, and **Remarks**. Vendor Identity owns the legal/display name, CR/VAT, company official number, company email and website. Primary Contact owns the named person, mobile/email and structured address/location fields (address, street number, district, city, region and postal code). The old Vendor `phone` column is migrated in place to `company_phone`, preserving existing data while removing it from the Primary Contact UI. `SourcingVendorContact` stores additional contact persons inside the same company boundary. A Vendor can have one active primary contact person; adding or editing a primary contact demotes the previous primary contact. Contacts are deactivated rather than destructively erased from normal application workflows.

New and edited Vendor records require Vendor name, display name, primary-contact mobile, primary-contact email, address, CR number and VAT number. Import uses the same required business fields, and Vendor export/search includes all newly separated identity and address data. Historical incomplete records remain deployable and lifecycle-safe; they are brought to the new completeness standard when edited.

## Lifecycle

Vendor operational visibility uses Active / Inactive. Archive removes the Vendor from the normal active/inactive working lists but is reversible. Delete means soft move to Trash for 30 days after exact Vendor-code confirmation and a reason; it is also reversible during retention. The application exposes no hard-delete action for Vendor masters.

Lifecycle changes affect Sourcing only. They never cascade into Inventory, Rental Manpower, Payroll, Documents or Accounting.

## Audit evidence

Every Vendor/contact mutation appends an immutable `AuditArea.SOURCING` event against `sourcing.SourcingVendor`. The Vendor profile Activity tab reads a bounded recent history. Audit events remain the authority for who changed a Vendor and when; they are not editable through this module.

## Release checks

Run `python3 scripts/verify-sourcing-vendor-master.py`, `python3 scripts/verify-sourcing-domain-foundation.py`, `python3 scripts/verify-sourcing-access-control.py`, and the normal production release/freeze gates. Deployment rehearsal must also run `python manage.py test apps.sourcing.tests.test_vendor_master --noinput` and the complete Django test suite.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.117.

> Vendor profile structure upgraded in SESCCO MS 1.0.117 with migration `0009_vendor_profile_structure.py`; the change is Sourcing-only and preserves the reference-only authority boundary.
