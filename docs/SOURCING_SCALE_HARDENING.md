# Sourcing Scale Hardening & Benchmarking — 1.0.111

This release certifies the independent Sourcing Directory for large reference datasets without changing its reference-only business meaning.

## Frozen benchmark volume

- 10,000 Sourcing Vendors
- 2,000 controlled Sourcing Materials
- 50,000 Vendor Supply Catalog references
- 5,000 Sourcing Manpower Suppliers
- 250 controlled Worker Trades
- 25,000 Workforce Catalog references

Use `python manage.py seed_sourcing_test_data --profile benchmark` on a disposable test company/database. The command uses the `SDEMO-` namespace and refuses to mix benchmark masters with non-SDEMO Sourcing masters unless `--allow-mixed-scale-seed` is explicit.

## Bounded browser surfaces

Directories, Material Finder and Workforce Finder remain server paged at 25/50/100 rows. Vendor Supply Catalog and Manpower Workforce profile tables are also server paged in this release, removing the previous unbounded profile hydration path.

Finder forms are progressively enhanced by `static/sourcing/js/finder-scale.js`. The enhancement debounces text/number input, aborts the previous GET through `AbortController`, and replaces only the bounded Finder root. Normal GET forms remain the no-JavaScript fallback.

## Query hardening

Vendor and Manpower directory counts use correlated subqueries. Contact search uses SQL `EXISTS`, avoiding join fanout and `DISTINCT` across high-cardinality contacts/offers. Additive Sourcing-only composite indexes support active Material/Trade + freshness and supplier/vendor Finder paths.

## Benchmark report

After benchmark seeding run:

```bash
python manage.py sourcing_scale_report --require-benchmark-volume --fail-on-limits
```

The report measures Vendor, Material, Manpower and Trade directories, both Finders, bounded profile catalogs, and the 5,000-row import parser. Default page budget is 12 SQL queries and 1.5 seconds per measured page. Timing is environment-sensitive; use it as a release-host guard, not a cross-hardware performance claim.

## Isolation

Sourcing benchmark seed, selectors and indexes only use `apps.sourcing`. They never create or update Inventory stock/suppliers, Rental Payroll suppliers/workers, assignments, timesheets, settlements, Projects or Accounting records.
