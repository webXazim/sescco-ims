# SESCCO IMS v1.0.130 — Project Manager Inventory Approval Hotfix

## Problem
Project stock receipts and transfers were blocked with "Assign a project inventory approver" even when an authorized Project Manager was assigned to the project via Administration or Project Pulse. The Inventory approval service checked only the separate `Project.inventory_manager` foreign key.

## Corrected approval selection
The inventory approval authority is resolved on each project, in priority order:

1. **Dedicated inventory approver** (`Project.inventory_manager`), if set. They must be active, have `inventory.stock.approve`, and have access to this project. If invalid, fail closed; never override them implicitly.
2. **Active Project Pulse manager**, if assigned. They must hold `inventory.stock.approve` and project scope. If invalid, fail closed rather than allow unrelated managers to bypass their assignment.
3. **Built-in Project Manager profile**, when neither of the above is assigned. Authorized managers with `Selected` scope can approve only those projects; managers with `All` scope can approve every project in their own company. Every user must have the *active* built-in Project Manager profile with the Inventory approval permission. Multiple eligible managers may exist; only one approval decision per project can be recorded under row locking.

The same authority resolution is used for request submission, pending approval visibility, deciding, and revalidation before posting stock. A transfer touching two projects still requires one approval per affected project. A requester can never approve their own stock request. Company isolation, historic approved decisions, immutable movements and approval audit remain enforced.

## Configuration notes
- In **Administration → Users**, assign the user's built-in Project Manager profile and choose `All` or `Selected` project scope. Grant access to the relevant company; the profile already has Inventory stock approval permission.
- Alternatively, assign them as the **Project Pulse manager** and explicitly grant Inventory stock approval in their access profile, or set **Dedicated inventory approver** in the project's details.
- The `Project manager` text field on a project is a label only and does not grant permissions.
- When a dedicated approver is configured, they have precedence even if other managers have All-project access.

## Validation
Source freeze, version/permission checks, syntax checks and archive integrity are verified offline. Django/PostgreSQL tests **must** run in Ubuntu staging before live deployment:

```sh
python manage.py check
python manage.py test apps.inventory.tests.test_project_stock_approvals --noinput
python manage.py test apps.inventory apps.projects apps.accounts --noinput
```

For Docker deployments, use your configured application container and environment, and preserve the production backup/restore workflow. No new database migration or version change is introduced. This remains v1.0.130.
