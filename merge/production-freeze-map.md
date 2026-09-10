# IMS + Payroll final production-freeze map

Upgrade 12 closes the 12-step merge program and freezes the merged application as the next production
baseline.

| Concern | Frozen production authority |
| --- | --- |
| Django project | IMS `config` |
| Authentication | `accounts.User` |
| Business context | `core.Company` / `accounts.CompanyMembership` |
| Shared Projects | `projects.Project` |
| Inventory | existing company-scoped IMS Inventory domain |
| Internal Payroll | `apps.internal_payroll` |
| Rental Manpower | `apps.rental_manpower` |
| Payroll documents | `apps.documents` |
| Management / Reports / Settings | merged platform-root APIs |
| Payroll UI | `/app/payroll/` + `static/payroll/` |
| Shared shell | `static/platform/` + common company/area switchers |
| Production Compose project | `ims` |
| Production PostgreSQL volume | `ims_postgres_data` |
| Rehearsal PostgreSQL volume | `ims_merge_rehearsal_postgres_data` |
| Release tasks | `scripts/release-tasks.sh` |
| Frozen production deploy entrypoint | `scripts/deploy-production-freeze.sh` |
| Upgrade 11 deployment authority | `scripts/deploy-production.sh` (unchanged) |
| Isolated rehearsal | `scripts/rehearse-production-freeze.sh` |
| Source freeze | `merge/production-freeze.sha256` |

The rehearsal project is intentionally a different persistence boundary. It exists only to prove a
real backup can survive the complete migration/reconciliation/regression path before the production
`ims` volumes are touched.
