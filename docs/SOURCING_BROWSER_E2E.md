# Sourcing Browser E2E + Production Freeze — 1.0.114

1.0.114 is the final Sourcing Directory feature freeze. It adds no schema and no new business authority. The release turns the completed Vendor and Manpower workflows into an explicit live-Chromium deployment gate.

## Required browser journey

Run the benchmark Sourcing seed in a disposable/rehearsal company, sign in with a user whose Access Profile has Vendor Sourcing edit, Manpower Sourcing edit, and the corresponding view permissions, then execute `scripts/certify-sourcing-browser-e2e.py` against the release URL.

The browser runner must complete these real UI paths: Vendor Directory → seeded Vendor profile → Supply Catalog → Material Finder rapid search → Verification History → Verify now → immutable history evidence; then Manpower Supplier Directory → seeded supplier profile → Workforce Catalog → Workforce Finder rapid search → Verification History → Verify now → immutable history evidence.

The fixed seed anchors are `SDEMO-V00001`, `SDEMO Material 0001`, `SDEMO-P00001`, and `SDEMO Trade 001`. The runner never creates or deletes a master record. Its only write is a confirmation revision on seeded Sourcing references.

## Browser limits

Finder result DOMs must remain bounded to 100 business rows. Rapid typing must preserve the final query, with the existing 350 ms debounce and `AbortController` stale-request cancellation. Any same-origin HTTP 5xx, uncaught page exception, or console error fails certification. A scenario exceeding the configured 10 second settle budget also fails.

## Evidence and operational boundary

Successful execution writes `sourcing-browser-certification.json`. Verification adds immutable Sourcing history only. The prior 1.0.110 runtime security certification remains mandatory and proves that Sourcing create/verify operations do not mutate installed Inventory, Projects, Internal Payroll, Rental Manpower, Documents, Data Exchange, or standalone Accounting models.

This browser runner is a deployment/rehearsal gate, not a substitute for the Django test suite, migrations, security certification, Sourcing scale report, Payroll browser certification, or production-freeze hashes.
