# User Management backend — 1.0.90

SESCCO MS 1.0.90 adds the production backend used by the Administration → Users interface planned for the next controlled release. It does not restore role-based authorization: every request continues to resolve application authority from `CompanyMembership.access_profile` and the profile's persisted permission grants.

## API surface

All endpoints require an authenticated active company membership. Read endpoints require `access.users.view` (or the corresponding profile-view authority); mutations require `access.users.manage`.

- `GET /api/access/users/` — bounded 25/50/100-row company user register with server search and status filtering.
- `POST /api/access/users/` — create a user, temporary credential, Access Profile and scopes atomically.
- `GET|PATCH|DELETE /api/access/users/<membership_id>/` — detail, safe update, and guarded delete of an unused onboarding identity.
- `POST /api/access/users/<membership_id>/status/` — activate/deactivate company access. If the identity has no other active company membership, deactivation also disables sign-in.
- `POST /api/access/users/<membership_id>/reset-password/` — administrator temporary-password reset.
- `GET /api/access/profiles/` — active company Access Profiles for assignment.
- `GET /api/access/scopes/lookup/?type=...&q=...` — bounded Project, Branch/Office or Inventory Location lookup for scope assignment.

Search terms require two characters when supplied. Scope lookup returns no more than 25 rows. User lists never hydrate the complete company user register in the browser.

## Credential handling

New users and administrator password resets pass Django password validation, set `must_change_password=true`, update `credentials_updated_at`, and call `set_password`. Changing the password hash invalidates existing Django authenticated sessions. Plaintext temporary passwords are never stored in audit events or response payloads.

The flag is intentionally exposed to the shell so the Administration/sign-in UX can enforce the forced-change journey in the later security-hardening step without changing the credential schema again.

## Owner and administrator safety

- A non-owner Access Administrator cannot assign the system `role-owner` profile.
- A non-owner cannot update, deactivate, or reset another Owner account.
- An administrator cannot change their own Access Profile/scopes or deactivate themselves through User Management.
- Existing final-active-owner protection remains in `CompanyMembership` and `User` model validation.
- Django `is_staff` remains reserved for actual Django superusers; SESCCO Access Administrators are normal application users.

## Scope semantics

Each membership has independent Project, Branch/Office and Inventory Location scope modes: `all`, `selected`, or `none`. A `selected` mode must contain at least one same-company record. Updates replace the normalized scope rows inside the same database transaction as the access update. IDs from another company are rejected before any replacement is committed.

## Deletion policy

Established identities are deactivated, not hard-deleted. Hard deletion is permitted only for an unused onboarding identity that has never signed in, has no actor audit history, has no domain-model references, belongs to no other company, is not an Owner, and passes exact-username confirmation. The delete decision itself is appended to the immutable Access audit ledger before the identity is removed.

## Deployment validation

Because 1.0.90 adds `accounts.0007_user_management_backend`, production rollout must run the normal isolated PostgreSQL rehearsal, `makemigrations --check --dry-run`, migration plan, `merge_access_report --fail-on-errors`, curated production E2E suite, and full Django regression suite before cutover.
