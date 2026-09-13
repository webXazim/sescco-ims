# Payroll scale seed profiles

SESCCO MS keeps the existing deterministic `functional` DEMO seed as the default. It remains the fastest fixture for exercising attendance, payroll, WPS, supplier settlements, payments, documents, reports and lifecycle behavior.

Release 1.0.61 adds two **optional** high-cardinality profiles for load and benchmark testing. They are intentionally restricted to a dedicated DEMO tenant with no non-DEMO Internal or Rental worker masters.

| Profile | Internal employees | Rental workers | Branches | Departments | Suppliers | Projects | History |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `functional` | 18 | 30 | functional fixture | functional fixture | functional fixture | functional fixture | current Draft + one closed E2E month |
| `realistic` | 250 | 750 | 6 | 12 | 8 | 12 | 6 closed scale months |
| `benchmark` | 2,000 | 5,000 | 15 | 24 | 30 | 40 | 12 closed scale months |

The scale profiles add daily Internal Attendance and Rental Timesheet rows, overtime, approved adjustments/advances, closed payroll snapshots, salary-payment/WPS rows, worker project-transfer history, supplier settlements, settlement lines and paid supplier-payment allocations. The benchmark profile therefore produces millions of daily rows and tens of thousands of financial snapshot rows by design.

## Run through deployment

```bash
./scripts/deploy-production.sh --seed
./scripts/deploy-production.sh --seed --seed-profile realistic
./scripts/deploy-production.sh --seed --seed-profile benchmark
```

The same profile may be selected with `IMS_SEED_PROFILE`. `IMS_SEED_BATCH_SIZE` controls chunk size for high-volume inserts; the default is 5,000 and values below 500 are rejected.

## Run the management command directly

```bash
python manage.py seed_payroll_test_data --profile functional
python manage.py seed_payroll_test_data --profile realistic
python manage.py seed_payroll_test_data --profile benchmark
```

Use `--company-slug` when more than one company is present and `--period YYYY-MM` to control the functional Draft period.

## Restart / idempotency behavior

Scale records use stable `DEMO-SCALE-*` / `RDEMO-SCALE-*` identities and stable financial references. Inserts are committed in bounded chunks with database uniqueness guards. If a very large seed is interrupted, rerun the **same profile**; the command fills missing rows and then verifies required population counts. Running `benchmark` after `realistic` expands the same scale population instead of creating a duplicate population. Running a smaller profile after a larger profile never shrinks or rewrites the already-created large dataset.

The functional E2E seed remains transactionally controlled. Scale history is deliberately separate from its live Draft and collision-safe closed E2E month so high-volume benchmark rows do not alter the canonical workflow fixture.

## Safety boundary

Do not use `realistic` or `benchmark` on production or on a tenant containing real/non-DEMO Internal employees or Rental workers. The command refuses that case. The scale generator never copies uploaded identity/bank information; names, IDs, phones, IBANs, suppliers, projects and financial references are synthetic.
