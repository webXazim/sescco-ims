# SESCCO IMS 1.0.130 — Project Manager All Projects Scope

## Behavior
- Administration → Users supports **Projects: All company projects** or **Selected only** for built-in Project Managers, at creation and update.
- All is dynamic and includes both existing and subsequently created projects within the manager’s company. `None` is not allowed for a built-in Project Manager.
- Access remains limited to the permissions granted by the assigned access profile and the separate inventory-location scope.
- Built-in Project Managers can view stock, movements and project-related transfers in their authorized projects, but not unrelated office-only stock.
- Inventory approvals are **not** automatically delegated just because a manager has All Projects scope: the project’s Inventory Approver must still be assigned explicitly and the manager cannot approve their own submitted request.
- Project Pulse expense, budget and profit permissions remain unchanged and confidential.
- The legacy membership creation route without an explicit project-scope choice is still blocked for the Project Manager role. Use Administration → Users.

## Change set
- `apps/accounts/user_management.py`, `apps/accounts/services.py`
- `apps/inventory/access.py`
- `static/platform/js/access-management.js`
- Django regression tests for Create/Edit/All/Selected/None, company isolation and Inventory approval assignment.
- Version/cache headers and active release verification.

## Data and deployment
No schema change or migration; no existing membership scopes are altered automatically. Apply the hotfix over 1.0.129 and update the production environment `APP_VERSION` to 1.0.130 through the existing version synchronization script. Back up the production database and source before deployment. Verify with `python manage.py check`, `python manage.py test apps.accounts.tests.test_user_management apps.inventory.tests.test_project_stock_approvals` (then full regression suite), and `python manage.py collectstatic --noinput`.

Production Django/PostgreSQL tests have **not** been run by this packaging environment; staging validation remains required.
