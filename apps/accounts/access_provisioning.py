from __future__ import annotations

from django.db import transaction

from .access_catalog import permissions_for_legacy_role, system_profile_key_for_role
from .models import AccessProfile, AccessProfilePermission
from .roles import AccessRole, role_definition


@transaction.atomic
def ensure_system_access_profile(*, company, role: str) -> AccessProfile:
    """Return the built-in profile represented by a legacy membership classification.

    The role value is provisioning metadata only from 1.0.89 onward. Runtime authorization
    never evaluates it; EffectiveAccess reads only the persisted AccessProfile grants.
    """

    if role == AccessRole.CUSTOM:
        raise ValueError("Custom memberships must be assigned an explicit AccessProfile.")
    definition = role_definition(role)
    profile, created = AccessProfile.objects.get_or_create(
        company=company,
        key=system_profile_key_for_role(role),
        defaults={
            "name": definition.label,
            "description": definition.description,
            "is_system": True,
            "is_active": True,
        },
    )
    if created:
        AccessProfilePermission.objects.bulk_create(
            [
                AccessProfilePermission(profile=profile, permission=permission.value)
                for permission in sorted(permissions_for_legacy_role(role), key=lambda item: item.value)
            ],
            batch_size=250,
        )
    return profile
