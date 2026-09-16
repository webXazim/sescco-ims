# Administration / Users UI — 1.0.91

SESCCO MS 1.0.91 exposes the company-scoped User Management backend through a normal Administration module. The UI is intentionally a client of the 1.0.90 APIs: hiding a button, changing a route, or modifying browser state cannot grant authority.

## Module access

`Administration` appears in the shared module switcher only when the active `CompanyMembership.access_profile` grants `access.users.view`. `/app/administration/` is protected by the same backend permission. Access Administrators remain ordinary application users; Django `/admin/` stays reserved for Django superusers.

## User register

The Users register requests `/api/access/users/` in bounded 25/50/100-row pages. Search is server-authoritative and requires at least two characters. Active/Inactive filtering is server-side. Rapid searches abort stale requests, and the current page stays visible while a replacement request is in flight.

## Add / edit user

Administrators with `access.users.manage` can create and update company users. Creation requires a temporary password, active Access Profile and explicit scope semantics. The password is submitted directly to the backend and is never written to browser storage. New users are marked for forced password change by the backend.

Editing a user can change identity fields and, where the backend permits it, the assigned Access Profile and scopes. An administrator cannot change their own Access Profile/scopes. Non-owner Access Administrators cannot modify Owner accounts or assign the Owner profile.

## Operational scopes

Project, Branch/Office and Inventory Location scopes each use `all`, `selected` or `none`. Selected records are found through the bounded `/api/access/scopes/lookup/` endpoint. The scope UI never hydrates complete project, branch or location masters.

A scope restricts permissions; it never creates permissions. For example, selecting a project for a user whose Access Profile has no Rental or Inventory permissions does not grant access to that project.

## Security actions

The user drawer exposes backend-authoritative flows for password reset, activation/deactivation and guarded deletion of an unused onboarding account. Established accounts are expected to be deactivated so historical attribution remains intact. Owner/self protections are shown in the interface but remain enforced by the service layer.

## Release validation

`merge/user-management-ui.json` and `scripts/verify-user-management-ui.py` freeze the Administration route, permission gate, bounded register, scope lookups, assets and security-action wiring. The Django UI regressions are also part of the curated production E2E runtime suite.
