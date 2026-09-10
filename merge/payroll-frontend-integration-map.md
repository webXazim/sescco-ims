# Payroll frontend integration

Upgrade 9 installs the frozen DocGen V2 Payroll frontend inside the authoritative merged IMS Django
project without replacing the existing Inventory frontend.

## URL and asset boundary

- Inventory continues using its existing server-rendered Django pages under `/app/` and its existing
  `static/css/styles.css` + `static/js/app.js` assets.
- Payroll is mounted as one merged workspace at `/app/payroll/`.
- Payroll static assets live only under `static/payroll/`.
- Payroll API calls remain at the platform root (`/api/internal/`, `/api/rental/`, `/api/documents/`,
  `/api/management/`, `/api/reports/`, `/api/settings/`). There is no second API server or proxy.
- Payroll print documents continue using `/documents/<uuid>/print/`.

The frozen Payroll JS/CSS source is copied from the production-freeze PRS revision recorded in
`merge/source-manifest.json`. The JS and all 52 CSS files remain byte-for-byte identical to that
source. Only the Django shell template is adapted to the merged static namespace. Upgrade 10 adds the
shared platform Business/Area switcher without modifying the frozen Payroll JS/CSS bundle.

## Server bootstrap authority

`apps.core.payroll_views.payroll_app` renders `templates/payroll/app.html` using the merged selectors:

- Internal employee/branch/department/salary/attendance/payroll/payment contexts from
  `apps.internal_payroll`
- Rental suppliers/workers/shared projects/assignments from `apps.rental_manpower`
- immutable document records from `apps.documents`
- Management/Reports source context from `apps.core.management`
- Company identity/settings from the unified `core.Company` / `CompanySettings`
- role/workspace/capability information from the active `accounts.CompanyMembership`

No fixture/prototype backend is shipped with the frontend.

## Authorization boundary

The Payroll shell itself requires an active company membership with at least one of Internal Payroll,
Rental Manpower, or Management workspace access. Inventory-only Storekeepers and Inventory Managers
cannot open `/app/payroll/`.

Every API endpoint continues enforcing its own workspace/capability checks independently, so browser
state cannot grant access.

Payroll-only roles now redirect from `/` to `/app/payroll/` instead of entering an Inventory-only
redirect loop. Users who also have Inventory access retain Inventory as the default authenticated home and can
switch areas through the unified Upgrade 10 platform switcher.

## Upgrade 10 integration

Upgrade 10 preserves the two purpose-built presentation engines but places one shared Business/Area
contract above them. Inventory and Payroll now use the same active company and module switcher while
the namespaced Payroll asset/API boundaries established here remain unchanged.
