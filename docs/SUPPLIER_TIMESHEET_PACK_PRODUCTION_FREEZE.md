# Supplier Timesheet Pack v3 — Production Freeze & Acceptance

Upgrade 14/14 closes the Rental supplier-document migration. The normal production path is now frozen as:

**Locked Project Timesheet → Supplier Monthly Timesheet Pack → Approved Supplier Settlement → Supplier Invoice Received → Paid Supplier Payment → Payment Advice**

The Supplier Monthly Timesheet Pack is operational evidence only. Settlement remains the financial authority, Supplier Invoice Received remains inbound from the supplier, and supplier acknowledgement records receipt rather than approval.

## Final source and document boundaries

- One v3 pack represents exactly one supplier + one project + one month + one Locked Rental Timesheet revision.
- Daily regular attendance/status is frozen per worker. Overtime remains one monthly total per worker and is never distributed across dates.
- The pack contains no rates, VAT, payable, gross/net or other commercial values.
- The supplier summary and every worker sheet reconcile to the same immutable snapshot.
- A worker-only print is derived from the finalized pack and does not create another `BusinessDocument`.
- Existing v2 Supplier Timesheet Statements remain immutable/readable as historical evidence.
- Normal creation uses the bounded type-first generator. The generic Documents POST remains closed to direct v3 pack creation.
- Project Timesheet remains an operational Project Timesheets output rather than a supplier-document creation purpose.

## Production reconciliation

Run after migrations and before treating the release as accepted:

```bash
python manage.py merge_documents_management_report --fail-on-errors
```

The reconciliation now understands both legacy supplier-qualified Rental Timesheet documents and v3 Supplier Timesheet Packs. For v3 it verifies:

- immutable snapshot fingerprint;
- schema 3.0 contract and worker/summary reconciliation;
- supplier-qualified source identity;
- source row/company ownership;
- snapshot source id/model binding;
- supplier code/entity-reference binding; and
- v3 source fingerprint binding to the immutable supplier/project/source/summary/worker payload.

This closes a transitional gap where the older merge reconciliation command only recognized the legacy `supplier_timesheet` variant and could reject a valid v3 pack once real v3 documents existed.

## Scale acceptance

On a rehearsal/test database with a Locked Rental supplier source:

```bash
python manage.py supplier_timesheet_pack_scale_report --fail-on-limits
```

For release-volume certification use a known 250-worker source:

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

The 8 MiB figure is a regression budget, never a truncation limit.

## Deployment acceptance

The production candidate is accepted only after all of these succeed in the deployment/rehearsal container:

```bash
python manage.py check --deploy --fail-level ERROR
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py merge_documents_management_report --fail-on-errors
bash scripts/certify-payroll-production-e2e.sh
```

For a release rehearsal, also run the full Django suite and the Supplier Timesheet Pack scale report against seeded or representative Locked data. No historical document rewrite is part of this freeze.
