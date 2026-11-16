# SESCCO IMS v1.0.130 — Permission-driven stock approval hotfix

This source-only hotfix fixes the discrepancy between Administration's custom-profile
**Project Inventory · Approve / Reject** grant and the backend's role/manager-only
authorization. It does not change DB schema, existing grant assignments or stock data.

## Exact policy

| Operation | Required permission | Scope / outcome |
| --- | --- | --- |
| Submit project stock receipt | `inventory.stock.receive` | Company, project and Inventory location must be accessible; creates a pending request, does not post stock |
| Submit project or office transfer | `inventory.stock.transfer` | Both locations must be in Inventory scope; any involved project(s) require approval before posting |
| Review and approve/reject | `inventory.stock.approve` | Active profile and membership, current company and project scope, regardless of profile name or manager designation |
| View approvals | `inventory.stock.approve`, `.receive`, `.transfer`, or `.view` | Approvers see project-scoped requests; submitters see their own; other requests hidden |
| Office-to-office transfers | `inventory.stock.transfer` | Post immediately, subject to existing stock/location validations |

A user who has Receive/Transfer but not Approve cannot decide. A user with
Approve but not Receive/Transfer cannot initiate those stock movements.

Pending stock requests can be submitted before an approver is configured. They
stay pending until someone is granted approval access; **stock balances are not
changed at submission**. Project-to-project transfers still require a separate
recorded decision for *each* project. A single reviewer may approve both rows
only if that reviewer has approval permission and both projects in scope.

Approvers cannot approve/reject their own requests. Project scopes cannot reach
another company. The final posting revalidates each recorded decision maker's
*current* approval permission and project scope, so revoked approvals cannot post.

`Project.inventory_manager` and Pulse Manager assignments are optional assignment
metadata; neither adds extra permissions nor blocks other eligible custom profiles.

## Deployment and verification

1. Back up the application, database and private attachments.
2. Extract hotfix over the verified v1.0.130 release.
3. Run `python3 scripts/verify-project-manager-approval-fallback.py`.
4. Run `sudo bash scripts/verify-production-freeze.sh`.
5. Review/commit the intended source changes. The production deploy requires a clean Git tree.
6. Run `python manage.py test apps.inventory.tests.test_project_stock_approvals` in the configured Django/PostgreSQL staging environment, then the full regression suite.
7. Deploy only after all tests pass.

No schema migration or APP_VERSION change. This release has been source-checked
and packaged, but full runtime regression must be verified on Ubuntu.
