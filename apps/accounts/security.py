from __future__ import annotations

from django.db.models import F

from .models import User


SESSION_SECURITY_VERSION_KEY = "_sescco_security_version"


def bump_user_security_version(user_or_id) -> None:
    """Invalidate every authenticated browser session for one SESCCO identity.

    Django's password hash already invalidates sessions after password changes. This
    independent monotonically increasing version also covers authorization-only changes
    such as Access Profile, scope and membership activation updates.
    """

    user_id = getattr(user_or_id, "pk", user_or_id)
    if not user_id:
        return
    User.objects.filter(pk=user_id).update(security_version=F("security_version") + 1)


def bump_profile_user_security_versions(profile) -> int:
    """Invalidate sessions for every identity assigned to an Access Profile."""

    user_ids = profile.memberships.values_list("user_id", flat=True)
    return User.objects.filter(pk__in=user_ids).update(security_version=F("security_version") + 1)


def stamp_security_session(request, user=None) -> None:
    identity = user or getattr(request, "user", None)
    if identity is None or not getattr(identity, "is_authenticated", False):
        return
    request.session[SESSION_SECURITY_VERSION_KEY] = int(identity.security_version)
