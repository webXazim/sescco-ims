# SESCCO IMS v1.0.131 — Pending stock transfer cancellation & approvals counter

## Behavior
- A pending, unposted **stock transfer** may be cancelled by its original requester, with a required reason.
- Cancellation is POST-only, company-scoped, and serialized with the approval transaction using the same row lock.
- Approved/rejected/already-posted transfers cannot be cancelled; receipt requests cannot be cancelled through this action.
- Cancellation does not create a stock movement or change balances. Earlier project decisions and the original request remain for audit.
- Cancelled requests appear under **Stock approvals → Status → Cancelled** with cancellation metadata and reason.
- **Stock approvals** sidebar displays the distinct count of pending requests visible to that user: their own submitted requests plus eligible in-scope approvals, never requests of another company. Two-project transfers count as one request.
- The requester sees a Cancel shortcut on pending transfer rows, leading to the cancellation form on the details page.

## Schema
- Migration `apps/inventory/migrations/0021_stock_request_cancellation.py` adds `cancelled` status, `cancelled_by` and `cancellation_reason`.
- Existing rows remain unchanged; this is an additive migration.

## Production acceptance
1. Back up the database and source. Deploy the full release or focused hotfix.
2. Ensure `.env.production` is set to `APP_VERSION=1.0.131` (deployment sync script can update this safely).
3. Run `python manage.py migrate`, `python manage.py check`, `python manage.py makemigrations --check --dry-run` and `python manage.py test apps.inventory.tests.test_project_stock_approvals` in staging.
4. Check that a requester's newly submitted transfer displays in Stock approvals and that the pending count increments.
5. Cancel it with a reason; verify status Cancelled, count decreases and stock quantity is unchanged.
6. Check that another user cannot cancel it and that a fully posted transfer cannot be cancelled.
7. Check scoped review visibility, company isolation, and project-to-project dual approval.

Static Python parsing and release-source checks do not substitute for Django/PostgreSQL testing on the server.
