# Supplier Timesheet Pack v3 — Scale & Production Certification

This release gate certifies the supplier-facing monthly timesheet document against the same immutable Locked Rental Timesheet authority used by the production generator. It does not create a second Payroll calculation path and it does not alter Settlement, Supplier Invoice or Supplier Payment authority.

## Release target

The packaged regression fixture contains **250 workers** for one supplier, one project and one 30-day month (7,500 daily attendance rows plus monthly overtime rows). The certified budgets are:

- snapshot aggregation: **2 SQL queries** — one supplier-scoped daily-entry query and one supplier-scoped monthly-OT query;
- full Supplier Timesheet Pack print-context build: **0 SQL queries**;
- derived worker-month print-context build: **0 SQL queries**;
- immutable snapshot payload for the 250-worker fixture: **< 8 MiB**;
- worker render units: exactly equal to `summary.worker_count`;
- summary sections: bounded at 18 worker rows per summary section;
- every worker export contains the complete calendar month and retains monthly-only overtime semantics.

The 8 MiB value is a release regression budget, not a runtime clipping limit. The application must fail validation rather than silently truncate authoritative workers or days.

## Runtime certification command

On a rehearsal or test database containing Locked Rental timesheet history:

```bash
python manage.py supplier_timesheet_pack_scale_report --fail-on-limits
```

The command automatically selects the largest eligible supplier/project/month group. To certify a specific source:

```bash
python manage.py supplier_timesheet_pack_scale_report \
  --company-slug <company-slug> \
  --period 2026-07 \
  --project-code <project-code> \
  --supplier-code <supplier-code> \
  --min-workers 250 \
  --max-aggregate-queries 2 \
  --max-print-queries 0 \
  --max-snapshot-mib 8 \
  --fail-on-limits
```

Elapsed milliseconds are reported so operators can compare releases on the same infrastructure, but elapsed time is intentionally not a portable release threshold because it depends on PostgreSQL cache state, CPU, disk and container load.

## Concurrency / retry behavior

Supplier Timesheet Pack finalization now takes a PostgreSQL row lock on the authoritative Locked `RentalTimesheetPeriod` before deciding whether a final pack already exists. Two simultaneous create requests for the same supplier/project/month therefore serialize at the source authority and return the same immutable `BusinessDocument`; they do not create duplicates or surface a unique-constraint 500 to one browser.

The source lock does not make the document mutable and does not change timesheet authority. Existing finalized documents are still integrity-verified before reuse.

## What this certification does not change

- No database migration is introduced.
- No finalized historical document is rewritten.
- Daily attendance and monthly overtime ownership remain in Rental Payroll.
- Settlement, Supplier Invoice Received, Supplier Payment and Accounting calculations are unchanged.
- Commercial rates/payables remain excluded from the Supplier Timesheet Pack.
