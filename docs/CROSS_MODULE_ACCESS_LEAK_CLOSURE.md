# Cross-module access leak closure — 1.0.97

Carried forward unchanged in SESCCO MS 1.0.99.

SESCCO MS 1.0.97 treats indirect data surfaces as authorization boundaries, not convenience views. A record that is hidden from its primary page must also be absent from global search, deep links, Documents, Reports, Archive/Trash, dashboard aggregates and lookup controls.

## Enforcement rules

- **Internal Branch scope:** employee directories and deep links use the employee's current Branch. Historical payroll/payment/report snapshots use the Branch captured on that immutable snapshot.
- **Rental Project scope:** workers, projects, settlements, payments, Documents and supplier lookup/results are limited to assigned Projects. Cross-project supplier financial totals are not projected into a narrowed scope.
- **Documents:** viewing and finalizing still requires the document permission, and the source/document must also be inside Branch/Project scope. Whole-company Internal Timesheet documents fail closed for Branch-restricted users.
- **Reports:** a generic Reports permission never unlocks sensitive Payroll/WPS/Payment/Settlement data. The underlying page permission is required too, and report rows/KPIs are scope-filtered.
- **Management:** company-wide overview/approval/audit surfaces require their exact underlying permissions. They fail closed whenever Branch, Project or Inventory Location scope is narrowed because those cross-domain aggregates cannot be safely inferred from partial data.
- **Archive/Trash:** recovery registers use the same Branch/Project scope as the live records.
- **Global search:** `shared.search.use` is mandatory. The browser only calls entity endpoints whose exact page permission is present; server APIs independently re-check permissions and scopes.

Hiding a button or route is never treated as the security control. Querysets, source selectors and direct API requests are authoritative.


> Carried forward and reverified unchanged in SESCCO MS 1.0.101.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.113.
