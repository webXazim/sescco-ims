# SESCCO IMS — Custom Access Profile User Transfer

## What changed
Administration → Access Profiles → open a built-in profile → Customize as New Profile.

1. Set the custom profile name, description, and exact permissions.
2. Choose **Create Custom Profile**. Before saving, the system displays a second
   confirmation step listing the users currently assigned to the original profile.
3. Select one option:
   - **Keep existing users** (default): create the custom profile without moving users.
   - **Move selected users**: search and tick only the required user accounts.
   - **Move all assigned users**: reassign every listed source-profile user.
4. Confirm **Create Custom Profile**. Creation and reassignment happen together.

## Security and data integrity
- A separate `access.users.manage` permission is required to move people. Profile
  creation alone still uses `access.profiles.manage`.
- Built-in source profile and its permissions remain unchanged.
- Source membership IDs are independently checked against the company, original
  profile and acting user. There is no cross-company reassignment.
- Bulk **All** uses the exact roster reviewed in the UI. If it changed before
  submission, the request fails and nothing is saved.
- An administrator cannot reassign their own account using this flow.
- Built-in Company Owner cannot be the source profile.
- The new profile and any user assignments are committed in a single database
  transaction; errors roll back all changes.
- Every changed user's existing browser sessions are invalidated, and full
  before/after snapshots are written to Access History, supporting recovery.
- Existing project, branch, and inventory location scopes remain unchanged.
- Both active and inactive assigned users appear in the roster; inactive
  users are marked, and All includes them.
- A profile move does not automatically update a project's designated
  inventory approver, and users still cannot approve their own requests.

## Production patch installation
Upload `sescco-ims-profile-user-transfer-hotfix.zip` to `/home/deploy/`, then:

```bash
cd /opt/sites/ims
sudo unzip -o /home/deploy/sescco-ims-profile-user-transfer-hotfix.zip -d /opt/sites/ims
python3 scripts/verify-custom-profile-user-transfer.py
sudo bash ./scripts/deploy-production.sh
```

## Focused Django test (run in your production Docker environment)
From a Django-equipped container/environment, run:

```bash
python manage.py test apps.accounts.tests.test_custom_access_profiles --noinput
python manage.py makemigrations --check --dry-run
```

No model changes or migrations are required. Static syntax, permission, access,
retention and regression-marker checks were run locally; Django DB integration
and live browser checks still need a configured Django environment.
