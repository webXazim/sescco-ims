# Sourcing Security, Tenant & Cross-module Isolation Certification

Release: **1.0.113**

This certification freezes the security boundary for the independent SESCCO MS Sourcing Directory. Sourcing answers who SESCCO can call and what that source most recently said it can provide. It does not become an operational supplier, stock, worker, payroll, project, document, or accounting authority.

## Certified boundaries

- Vendor Sourcing and Manpower Sourcing remain independently permissioned. Vendor-only users cannot read Manpower Sourcing, and Manpower-only users cannot read Vendor Sourcing.
- `sourcing.*.view` is read-only. Direct POST requests to create, edit, lifecycle, catalog, verification, or master endpoints still require the matching `manage` permission and return HTTP 403 otherwise.
- Every Sourcing selector, service, and object lookup remains company scoped. A membership operating in Company A cannot read or mutate Company B Sourcing rows.
- Material Finder and Workforce Finder exclude inactive offers/trades/materials and archived, trashed, or inactive parent sources.
- Vendor and Workforce verification revisions remain append-only: queryset update/delete and instance rewrite/delete are blocked.
- Access Profile permission changes increment assigned users' `security_version`; an already-authenticated stale session is revoked on its next request.
- Sourcing create/verify paths must leave every installed operational app row count unchanged. The certification covers Inventory, Projects, Internal Payroll, Rental Manpower, Documents, and Data Exchange, and automatically includes a standalone Accounting app if one is introduced later.
- Sourcing models retain the deployment-time relation check that rejects database foreign keys into operational applications.

## Runtime certification

Run:

```bash
python manage.py test apps.sourcing.tests.test_security_certification --noinput
```

The test suite exercises actual Django middleware, URL permission gates, company context, Finder selectors, immutable revision managers, Access Profile session invalidation, and real Sourcing service writes.

## Static release gate

Run:

```bash
python scripts/verify-sourcing-security-certification.py
```

The static gate verifies this document, the runtime suite, the domain isolation check, the permission guards, the immutable-history implementation, the session-security hook, and release-task registration.

## Production rule

A 1.0.113 deployment is not certified until the full Django runtime suite and this focused certification suite pass against the release image/database during rehearsal. Static verification alone is not runtime evidence.
