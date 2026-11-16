# SESCCO IMS v1.0.130 — Payroll module visibility and transfer approval navigation

## Problem
The common platform module switcher treated generic Management workspace access (e.g. `settings.view`) as Payroll access. An Inventory-only custom access profile with such a setting could see a Payroll link and open the generic Payroll management shell, despite having no Internal Payroll or Rental Manpower permissions.

Transfer approval/rejection already existed under Inventory → Project approvals, but pending transfers were not visible in the completed transfer history, and the request inbox lacked a transfer-only filter and prominent links.

## Changes
- Payroll module authorization and `/app/payroll/` route now require **Internal Payroll** or **Rental Manpower** access. Management/Settings/Administration-only grants no longer unlock Payroll. The legacy Payroll management-only shell is not exposed without an actual Payroll workspace grant.
- Custom access profiles with both Inventory and a genuine Payroll permission retain both modules.
- Rename the Inventory menu item to **Stock approvals**; existing URL `/app/approvals/` is unchanged.
- Add request-type filters (All requests / Stock transfers / Stock additions) while keeping Pending, Approved, and Rejected status filters; approval inbox shows a clear Review action.
- Add **Pending transfer approvals** shortcuts in both Transfer history and New transfer pages.
- Existing project-scoped Approve / Reject checks, self-approval prohibition, multi-project transfer decisions, company boundaries, and posted-stock immutability remain unchanged.
- Add Django regression tests for module visibility/deep-link denial and transfer request filtering.

## User flow
1. The user with **Inventory · Stock · Transfer** creates a project transfer (pending, no immediate stock movement).
2. Another user with **Project Inventory · Approve / Reject** for the affected project opens **Inventory → Stock approvals** or **Transfers → Pending transfer approvals**.
3. Choose **Pending** and **Stock transfers**, open the request, review quantities, and Approve/Reject for each applicable project.
4. For project-to-project transfers both project decisions are required; only after the final valid approval is stock posted. A requester cannot approve their own submission.
5. **Transfer history** lists posted transfers; pending requests remain in the approval inbox.

## Deployment
Source version remains **1.0.130**. No database migration, permission-catalog change, or financial-data rewrite. Back up before deployment. Apply the hotfix, run `bash scripts/verify-production-freeze.sh`, and execute the Django tests on a staging PostgreSQL database before production. Review and commit intended changes before the normal production deployment.

Suggested targeted tests:

```
python manage.py test apps.accounts.tests.test_user_management_ui apps.core.tests.test_payroll_frontend apps.inventory.tests.test_project_stock_approvals
```

The integration tests were not executed in this offline packaging environment; they must run in the configured Django/PostgreSQL deployment.
