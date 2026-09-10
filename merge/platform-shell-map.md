# Unified platform shell

Upgrade 10 establishes one platform-level navigation contract across the merged Inventory and Payroll modules.
It does not merge the two presentation engines into one JavaScript bundle: Inventory keeps its server-rendered
Django pages and Payroll keeps its frozen DocGen V2 renderer. The shared shell layer owns the context above those
module-specific navigation systems.

## Shared hierarchy

1. **Business** — the active `core.Company` resolved from the authenticated `CompanyMembership` session.
2. **Area** — `Inventory Management` or `Payroll Management`, shown only when the active membership grants access.
3. **Module navigation** — Inventory navigation when Inventory is active; Internal Company / Rental Manpower /
   Management plus Payroll page navigation when Payroll is active.
4. **Account** — the same authenticated `accounts.User` and company membership role in both modules.

The reusable template is `templates/partials/platform_switchers.html`. The shared static layer lives under
`static/platform/` and is loaded by both `templates/base.html` and `templates/payroll/app.html`.

## Company switch safety

A company switch submits the current area key. The server activates only an active membership for the destination
company. It preserves the requested area only when that destination membership is authorized for it; otherwise it
redirects through `accounts:home`, which selects an area the destination membership can actually open.

This intentionally returns to the area home instead of preserving an object-detail URL, because an object identifier
from Company A must never be carried into Company B as navigation state.

## Module boundaries retained

- Inventory assets remain `static/css/styles.css` + `static/js/app.js`.
- Payroll assets remain under `static/payroll/` and keep frozen source parity.
- Shared shell assets use only `static/platform/`.
- No database migration is required for Upgrade 10.
- Module selection never changes authorization. Every Django view/API/service still checks its own workspace and
  capability contract against `request.company_membership`.
