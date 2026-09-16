# Access History and guarded recovery — 1.0.98

Carried forward unchanged in SESCCO MS 1.0.99.
SESCCO MS 1.0.98 exposes the existing immutable Access audit ledger directly inside Administration without creating a second history store. Users with `access.audit.view` can review company-scoped user, Access Profile, credential-security and access-recovery events through a bounded server-paged API and UI.

## Authority boundary

Viewing Access History requires the exact `access.audit.view` permission. It does not imply `access.users.manage` or `access.profiles.manage`. A read-only auditor can inspect access changes but cannot modify a user or profile.

Guarded prior-access recovery is intentionally stricter. The actor must have both `access.audit.view` and `access.users.manage`. Recovery is blocked for the actor's own membership, and existing Company Owner protections continue to apply. Only the `before` snapshot from a supported immutable user-access event can be selected.

## What recovery changes

A recovery may reapply only:

- the historical company Access Profile;
- Project, Branch/Office and Inventory Location scope modes and selected IDs;
- company membership active/inactive state; and
- the recorded account active/inactive flag.

Usernames, email addresses, names and passwords are never rolled back from audit JSON. Temporary passwords are never exposed by Access History.

Before applying a recovery, the backend revalidates the historical Access Profile against the current company, requires it to be active when restoring active access, revalidates every selected Project/Branch/Location against current lifecycle rules, and applies the final-active-owner safeguards. The operator must type the target username exactly.

Every successful recovery increments the target user's session security version, invalidating existing browser sessions on the next request, and appends `access.user.access_restored` to the same immutable ledger with the source event ID/action. Recovery never edits or deletes the source audit event.

## Scale and retention

The Access History register uses page-size-plus-one pagination (25/50/100 rows) and does not fetch the complete audit ledger or issue an exact total-count query for normal browsing. Search requires at least two characters and remains company-scoped.

No new database table or migration is introduced in 1.0.98. Existing `core_audit_event` retention and immutability rules remain authoritative.

## Production validation

Run:

```bash
python3 scripts/verify-access-history-recovery.py
python3 scripts/verify-credential-session-revocation.py
python3 scripts/verify-production-freeze.sh
```

The production rehearsal must still run the complete Django regression suite before cutover.


> Carried forward and reverified unchanged in SESCCO MS 1.0.101.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.102.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.106.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.107.

> Carried forward and reverified unchanged where applicable in SESCCO MS 1.0.113.
