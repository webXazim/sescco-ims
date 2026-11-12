#!/usr/bin/env python3
"""Static release guard for audited built-in profile clone/user transfers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, markers: tuple[str, ...]) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in content:
            raise SystemExit(f"PROFILE CLONE USER TRANSFER ERROR: {path}: missing {marker}")


require("apps/accounts/access_profiles.py", (
    'def assigned_profile_users(',
    'def _requested_profile_reassignments(',
    'AccessPermission.ACCESS_USERS_MANAGE',
    'role-owner',
    'select_for_update()',
    'Source-profile assignments changed. Review the users and try again.',
    'You cannot change your own Access Profile.',
    'from .user_management import _identity_snapshot',
    'bump_user_security_version(member.user_id)',
    'action="access.user.updated"',
    '"profile_clone_user_reassignment": True',
))
require("apps/accounts/access_api.py", (
    'assigned_profile_users(',
    'request.GET.get("assigned_to")',
    '"assignedUsersForClone"',
))
require("static/platform/js/access-management.js", (
    'Customize as New Profile',
    'Choose users to move',
    'Keep existing users on the built-in profile',
    'Move selected users',
    'Move all',
    'expectedMembershipIds',
    'sourceProfileId',
    'assignmentMode',
    'isSelf ? "disabled"',
))
require("apps/accounts/tests/test_custom_access_profiles.py", (
    'test_clone_selected_moves_only_chosen_users_and_preserves_scopes',
    'test_clone_all_moves_full_reviewed_roster',
    'test_clone_stale_all_roster_aborts_creation',
    'test_clone_cannot_change_own_profile_even_with_bulk_all',
    'test_clone_reassignment_requires_user_management_permission',
))
print("PASS: Profile clone user selection, all-user review, tenant/self guards, atomic audit and session invalidation markers verified.")
