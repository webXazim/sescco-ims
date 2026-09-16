# Page-level View Only and Custom Access Profiles — 1.0.97

Carried forward unchanged in SESCCO MS 1.0.99.

SESCCO MS authorizes pages and actions from one company-scoped Access Profile. Custom profiles contain exact permission keys; a `*.view` permission opens only that page/data surface and never grants a mutation. Actions require their corresponding page-view permission plus the action permission.

Built-in profiles are immutable. Custom profiles may be created, revised, deactivated when unused, and guarded-deleted only when unassigned. An administrator cannot modify the profile currently granting their own authority. Every profile mutation is written to the immutable Access audit ledger.

The Payroll browser consumes the server-issued effective permission snapshot for navigation and route fallback. Internal Payroll APIs independently enforce exact GET/read and POST/PATCH/DELETE action permissions, so hiding a control is never the security boundary. The initial Payroll HTML bootstrap follows the same page permissions and does not include attendance roster data for an Employee-only viewer.

Examples:

- `internal.employees.view` — Internal Employees only, read-only.
- `internal.employees.view` + `internal.attendance.view` — Employees and Attendance, read-only.
- `rental.workers.view` + `rental.timesheets.view` — Rental Workers and Timesheets, read-only, subject to the user's Project scope.

Project, Branch/Office and Inventory Location scopes remain membership-owned and are applied in addition to page permissions. Custom profiles do not bypass the Foreman or Storekeeper scope contracts.


> Carried forward and reverified unchanged in SESCCO MS 1.0.101.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.108.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.115.
