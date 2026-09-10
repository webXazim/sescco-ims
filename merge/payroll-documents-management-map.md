# Payroll Documents / Management / Audit merge

Upgrade 8 imports the remaining cross-payroll read/document domains from the frozen PRS source into
the authoritative IMS Django platform.

## Authority mapping

| Standalone PRS concept | Merged platform authority |
| --- | --- |
| Payroll `BusinessDocument` | `apps.documents.BusinessDocument` in the IMS database |
| PRS `Company` / settings | merged `core.Company` / `core.CompanySettings` |
| PRS user / membership | existing IMS `accounts.User` / merged `CompanyMembership` |
| PRS audit | merged immutable `core.AuditEvent` |
| PRS numbering | merged `core.NumberSequence` service |
| Internal document sources | merged `apps.internal_payroll` |
| Rental document sources | merged `apps.rental_manpower` using canonical `projects.Project` |

## Document boundary

`BusinessDocument` is an immutable historical snapshot, not a second accounting/payroll ledger.
Documents may only be finalized from controlled source states (for example Locked timesheets,
Approved-or-later payroll/settlements, or Paid payment rows). Source lookup is always company-scoped.
The stored snapshot has a SHA-256 fingerprint and cannot be updated or deleted through the model,
queryset, API, or Django admin.

Preserved API contracts:

- `/api/documents/`
- `/api/documents/sources/`
- `/api/documents/<uuid>/`
- `/documents/<uuid>/print/`
- `/api/management/`
- `/api/reports/`
- `/api/reports/export.csv`
- `/api/settings/`

## Management/report boundary

Management and Reports are read models over the merged Internal Payroll, Rental Manpower, payment,
and audit tables. They do not persist a second set of totals. Every domain queryset is explicitly
company-scoped. Audit rows are included only for memberships with `VIEW_AUDIT`; report workspaces are
authorized through the active CompanyMembership.

CSV exports neutralize spreadsheet formula prefixes before writing cells.

## Production reconciliation

After migrations run:

```bash
python manage.py merge_documents_management_report --fail-on-errors
```

The command verifies company settings coverage, document snapshot integrity, document source
existence/company ownership, and audit actor-membership company consistency.
