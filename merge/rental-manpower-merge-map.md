# Rental Manpower backend merge map

Upgrade 7 imports the standalone PRS Rental Manpower domain into the authoritative IMS Django
project without importing a second User, Company, Project, or deployment stack.

## Authority mapping

| Standalone PRS concept | Merged authority |
| --- | --- |
| PRS `accounts.User` | existing IMS `accounts.User` |
| PRS membership/roles | merged `accounts.CompanyMembership` / role matrix |
| PRS `core.Company` | merged `core.Company` |
| PRS audit/numbering | merged `core` services |
| PRS `RentalProject` UUID PK | `projects.Project.reference` UUID at API boundary |
| Rental database project FK | existing integer `projects.Project.pk` |
| Manpower supplier | remains `rental_manpower.ManpowerSupplier` |
| Rental worker | remains `rental_manpower.RentalWorker` |

## Shared Project rules

- No `rental_project` table is created.
- Rental project endpoints list/create/update the canonical Project master.
- `/api/rental/...` never needs to expose the legacy integer Project PK.
- New Rental assignments require an active, non-trashed shared Project.
- Project work dates are validated through the shared project lifecycle contract.
- Project completion still requires settled Inventory balances and Rental assignments.
- Project Archive/Delete is a reversible lifecycle boundary: existing Rental assignments remain intact but project operations are suspended until restore or transfer/release.
- Historical assignments/timesheets/settlements protect physical Project deletion and are never cascade-erased.

## Rental domains retained

- manpower suppliers and worker master
- effective-dated assignment/transfer/trade/rate lifecycle
- project monthly timesheets, overtime, submit/approve/lock lifecycle
- worker adjustments
- immutable supplier settlement snapshots
- supplier payment/allocation/result/retry lifecycle
