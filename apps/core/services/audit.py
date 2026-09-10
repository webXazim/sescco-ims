from __future__ import annotations

from collections.abc import Mapping
import ipaddress
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from apps.core.models import AuditArea, AuditEvent


def _client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    remote_value = request.META.get("REMOTE_ADDR") or None
    if not remote_value:
        return None
    try:
        remote_ip = str(ipaddress.ip_address(remote_value))
    except ValueError:
        return None

    trusted = False
    for entry in getattr(settings, "TRUSTED_PROXY_IPS", []):
        try:
            if ipaddress.ip_address(remote_ip) in ipaddress.ip_network(str(entry), strict=False):
                trusted = True
                break
        except ValueError:
            continue

    if trusted:
        forwarded = request.META.get("HTTP_X_REAL_IP", "").strip()
        if not forwarded:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return remote_ip


def record_audit_event(
    *,
    company,
    area: AuditArea | str,
    action: str,
    object_type: str,
    object_id: object,
    actor_membership=None,
    actor=None,
    object_label: str = "",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    """Append an immutable audit event inside the caller's transaction.

    ``actor_membership`` is optional until Upgrade 3 introduces the unified membership model;
    existing IMS actions can already audit directly against ``accounts.User`` via ``actor``.
    """

    try:
        normalized_area = AuditArea(area).value
    except ValueError as exc:
        raise ValueError(f"Unknown audit area: {area}") from exc

    normalized_action = action.strip()
    normalized_object_type = object_type.strip()
    normalized_object_id = str(object_id).strip()
    if not normalized_action or len(normalized_action) > 100:
        raise ValueError("Audit action must contain 1 to 100 characters.")
    if not normalized_object_type or len(normalized_object_type) > 120:
        raise ValueError("Audit object_type must contain 1 to 120 characters.")
    if not normalized_object_id or len(normalized_object_id) > 64:
        raise ValueError("Audit object_id must contain 1 to 64 characters.")

    if actor_membership is not None:
        if actor is None:
            actor = actor_membership.user
        if actor_membership.company_id != company.pk:
            raise ValueError("Audit actor membership must belong to the audited company.")

    if actor is not None:
        display_name = actor.get_full_name().strip() or actor.username
        username = actor.username
        email = actor.email
    else:
        display_name = ""
        username = ""
        email = ""

    request_id = str(getattr(request, "request_id", "") or "")[:64] if request is not None else ""
    user_agent = (request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:500]

    return AuditEvent.objects.create(
        company=company,
        area=normalized_area,
        action=normalized_action,
        object_type=normalized_object_type,
        object_id=normalized_object_id,
        object_label=object_label.strip()[:240],
        actor=actor,
        actor_membership_id=getattr(actor_membership, "id", None),
        actor_role=str(getattr(actor_membership, "role", ""))[:40],
        actor_username=username,
        actor_display_name=display_name,
        actor_email=email,
        before=dict(before or {}),
        after=dict(after or {}),
        metadata=dict(metadata or {}),
        request_id=request_id,
        ip_address=_client_ip(request),
        user_agent=user_agent,
    )
