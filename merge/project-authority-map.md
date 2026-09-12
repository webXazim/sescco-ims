# Canonical shared Project authority

Upgrade 5 makes `apps.projects.Project` the only project master for the merged platform.
Inventory keeps its existing integer foreign keys. Payroll/Rental APIs use the immutable UUID
`Project.reference` as their public identifier and resolve it through `apps.projects.contracts`.

## Standalone Payroll source mapping

| PRS RentalProject | Merged projects.Project |
| --- | --- |
| UUID primary key | `reference` UUID (public/API identity) |
| `company` | `company` |
| `code` | `code` |
| `name` | `name` |
| `client_name` | `client_name` |
| `location` | `location` |
| `start_date` | `start_date` |
| `end_date` | `end_date` |
| `manager_name` | `manager_name` |
| Active / On Hold / Completed | Active / On Hold / Completed |
| — | Archived (shared platform lifecycle) |
| `notes` | `notes` |

`expected_completion_date` remains an IMS planning field and is available to both modules.

## Upgrade 7 requirements

When Rental Manpower is imported:

- Do **not** create or migrate `rental_manpower.RentalProject`.
- `WorkerAssignment.project`, `RentalTimesheetPeriod.project`, settlement project FKs and all
  Rental selectors/services must target `projects.Project`.
- External/API project IDs must use `Project.reference`; database FKs may use the existing integer
  `Project.pk` internally.
- Rental assignment/date validation must call the shared project contract or equivalent company-
  scoped checks.
- Project completion must account for both Inventory balances and open Rental assignments before
  the lifecycle transition is accepted.
- Archive/Delete may suspend the project with existing Inventory/Rental scope; protected history remains intact and prevents unsafe physical deletion.

Django deploy checks intentionally fail if a second model named
`rental_manpower.RentalProject` is installed.
