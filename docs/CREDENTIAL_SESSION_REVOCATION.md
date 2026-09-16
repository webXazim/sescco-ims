# Credential and session revocation hardening — 1.0.97

Carried forward unchanged in SESCCO MS 1.0.99.

SESCCO MS 1.0.97 makes authorization changes effective at the browser-session boundary, not only at the next protected backend action. Every user identity now carries a monotonically increasing `security_version`. An authenticated session stores the version it was issued against; when a security-sensitive administrator action increments the server version, the next request from the old session is rejected and the identity must sign in again.

## Changes that revoke existing sessions

The server increments the affected identity's security version when an administrator changes the user's Access Profile, Project/Branch/Inventory Location scopes, membership active state, or temporary password. Editing the permission set or active state of a custom Access Profile increments the version for every identity assigned to that profile. Legacy role-management services and Django-superuser membership corrections use the same revocation rule.

Password hash rotation continues to provide Django's native password-session invalidation. The independent security version covers authorization-only changes that do not alter the password hash and prevents a deactivated-then-reactivated account from reusing a browser session created before the status change.

## Temporary password enforcement

User Management still creates accounts with a temporary password and `must_change_password=True`. In 1.0.97 that state is now enforced:

- normal pages redirect to `/account/password/change/`;
- operational `/api/` requests return HTTP `428` with `code=password_change_required`;
- the password-change page and POST logout remain available;
- a successful password change clears the mandatory flag, rotates the session authentication hash, increments the security version, stamps the current session with the new version, and records an Access audit event.

Administrators cannot see the replacement password. The existing Django password validators remain authoritative, including the 12-character minimum configured by SESCCO MS.

## Stale-session response

When an authenticated request presents an older session security version, HTML requests are signed out and redirected to the login page with an access-changed message. `/api/` requests receive HTTP `401` with `code=session_revoked`. The security check runs immediately after Django authentication and before company/module authorization.

Sessions created before the 1.0.97 deployment do not contain a security-version stamp. Their first authenticated request is stamped with the current server version so the migration does not unnecessarily sign out every user at cutover; every later security change is revocation-enforced.

## Production migration

Upgrade 1.0.97 adds `accounts.User.security_version` through `apps/accounts/migrations/0011_user_security_version.py`. Rehearse and apply the packaged migration through the existing production deployment flow. No Payroll formula, Rental settlement formula, Inventory quantity formula, or lifecycle-retention behavior changes in this release.


> Carried forward and reverified unchanged in SESCCO MS 1.0.101.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.111.
