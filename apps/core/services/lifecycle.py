from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import HttpRequest

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event


class LifecycleAction(StrEnum):
    """Cross-module master-data lifecycle operations.

    This authority intentionally does not model domain workflows such as payroll approval,
    settlement approval, payment reversal, or inventory movement reversal. Those remain in
    their owning domain services. It governs only reusable master-record lifecycle concerns.
    """

    ARCHIVE = "archive"
    RESTORE = "restore"
    DELETE = "delete"
    DEACTIVATE = "deactivate"


@dataclass(frozen=True, slots=True)
class LifecycleBlocker:
    code: str
    message: str
    field: str = "record"
    label: str = ""
    count: int | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "field": self.field,
        }
        if self.label:
            payload["label"] = self.label
        if self.count is not None:
            payload["count"] = self.count
        return payload


@dataclass(frozen=True, slots=True)
class LifecycleDecision:
    action: LifecycleAction
    allowed: bool
    blockers: tuple[LifecycleBlocker, ...] = ()
    reason_required: bool = False
    confirmation_required: bool = False
    confirmation_token: str = ""
    evidence: Mapping[str, int] = field(default_factory=dict)
    policy_name: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "reasonRequired": self.reason_required,
            "confirmationRequired": self.confirmation_required,
            "confirmationToken": self.confirmation_token,
            "blockers": [item.as_dict() for item in self.blockers],
            "evidence": dict(self.evidence),
            "policy": self.policy_name,
        }


class LifecyclePolicy:
    """Base policy for a lifecycle-managed master record.

    Module policies own domain-specific dependency knowledge while this service owns the
    evaluation contract, input guards, standardized decisions, and audit metadata.
    """

    area: AuditArea | str = AuditArea.CORE
    object_type = ""
    supported_actions: frozenset[LifecycleAction] = frozenset()
    reason_required_actions: frozenset[LifecycleAction] = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions: frozenset[LifecycleAction] = frozenset({LifecycleAction.DELETE})

    @property
    def name(self) -> str:
        return type(self).__name__

    def label(self, instance: Any) -> str:
        return str(instance)

    def confirmation_token(self, instance: Any) -> str:
        return ""

    def dependency_evidence(self, instance: Any, action: LifecycleAction) -> Mapping[str, int]:
        return {}

    def blockers(
        self,
        instance: Any,
        action: LifecycleAction,
        *,
        evidence: Mapping[str, int],
    ) -> Iterable[LifecycleBlocker]:
        return ()


_POLICY_REGISTRY: dict[type[Any], LifecyclePolicy] = {}


def register_lifecycle_policy(model: type[Any], policy: LifecyclePolicy, *, replace: bool = False) -> None:
    if model in _POLICY_REGISTRY and not replace:
        raise ImproperlyConfigured(f"Lifecycle policy already registered for {model!r}.")
    if not policy.object_type.strip():
        raise ImproperlyConfigured(f"Lifecycle policy {policy.name} must declare object_type.")
    _POLICY_REGISTRY[model] = policy


def get_lifecycle_policy(instance_or_model: Any) -> LifecyclePolicy:
    model = instance_or_model if isinstance(instance_or_model, type) else type(instance_or_model)
    policy = _POLICY_REGISTRY.get(model)
    if policy is not None:
        return policy
    for parent in model.__mro__[1:]:
        policy = _POLICY_REGISTRY.get(parent)
        if policy is not None:
            return policy
    raise ImproperlyConfigured(f"No lifecycle policy is registered for {model!r}.")


def _normalize_action(action: LifecycleAction | str) -> LifecycleAction:
    if isinstance(action, LifecycleAction):
        return action
    normalized = str(action).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "archive": LifecycleAction.ARCHIVE,
        "restore": LifecycleAction.RESTORE,
        "restore_archive": LifecycleAction.RESTORE,
        "delete": LifecycleAction.DELETE,
        "delete_unused": LifecycleAction.DELETE,
        "deactivate": LifecycleAction.DEACTIVATE,
        "inactive": LifecycleAction.DEACTIVATE,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError({"action": "Unknown lifecycle action."}) from exc


def lifecycle_decision(
    instance: Any,
    action: LifecycleAction | str,
    *,
    reason: str | None = None,
    confirmation: str | None = None,
    validate_inputs: bool = False,
) -> LifecycleDecision:
    normalized_action = _normalize_action(action)
    policy = get_lifecycle_policy(instance)
    evidence = dict(policy.dependency_evidence(instance, normalized_action))
    blockers: list[LifecycleBlocker] = []

    if normalized_action not in policy.supported_actions:
        blockers.append(
            LifecycleBlocker(
                code="action_not_supported",
                field="action",
                message=f"{normalized_action.value.title()} is not supported for this record.",
            )
        )
    else:
        blockers.extend(policy.blockers(instance, normalized_action, evidence=evidence))

    reason_required = normalized_action in policy.reason_required_actions
    confirmation_required = normalized_action in policy.confirmation_required_actions
    confirmation_token = policy.confirmation_token(instance) if confirmation_required else ""

    if validate_inputs and not blockers:
        if reason_required and not (reason or "").strip():
            blockers.append(
                LifecycleBlocker(
                    code="reason_required",
                    field="reason",
                    message=f"A reason is required to {normalized_action.value} this record.",
                )
            )
        if confirmation_required and confirmation_token:
            if (confirmation or "").strip().casefold() != confirmation_token.strip().casefold():
                blockers.append(
                    LifecycleBlocker(
                        code="confirmation_mismatch",
                        field="confirmation",
                        message=f"Type {confirmation_token} to confirm deletion.",
                    )
                )

    return LifecycleDecision(
        action=normalized_action,
        allowed=not blockers,
        blockers=tuple(blockers),
        reason_required=reason_required,
        confirmation_required=confirmation_required,
        confirmation_token=confirmation_token,
        evidence=evidence,
        policy_name=policy.name,
    )


def require_lifecycle_action(
    instance: Any,
    action: LifecycleAction | str,
    *,
    reason: str | None = None,
    confirmation: str | None = None,
) -> LifecycleDecision:
    decision = lifecycle_decision(
        instance,
        action,
        reason=reason,
        confirmation=confirmation,
        validate_inputs=True,
    )
    if decision.allowed:
        return decision
    first = decision.blockers[0]
    raise ValidationError({first.field: first.message})


def lifecycle_capabilities(instance: Any) -> dict[str, object]:
    policy = get_lifecycle_policy(instance)
    decisions = {
        action: lifecycle_decision(instance, action)
        for action in (
            LifecycleAction.ARCHIVE,
            LifecycleAction.RESTORE,
            LifecycleAction.DELETE,
            LifecycleAction.DEACTIVATE,
        )
    }
    return {
        "policy": policy.name,
        "canArchive": decisions[LifecycleAction.ARCHIVE].allowed,
        "canRestore": decisions[LifecycleAction.RESTORE].allowed,
        "canDelete": decisions[LifecycleAction.DELETE].allowed,
        "canDeactivate": decisions[LifecycleAction.DEACTIVATE].allowed,
        "archiveReasonRequired": LifecycleAction.ARCHIVE in policy.reason_required_actions,
        "actions": {action.value: decision.as_dict() for action, decision in decisions.items()},
    }


def can_archive(instance: Any) -> bool:
    return lifecycle_decision(instance, LifecycleAction.ARCHIVE).allowed


def can_restore(instance: Any) -> bool:
    return lifecycle_decision(instance, LifecycleAction.RESTORE).allowed


def can_delete(instance: Any) -> bool:
    return lifecycle_decision(instance, LifecycleAction.DELETE).allowed


def delete_blockers(instance: Any) -> tuple[LifecycleBlocker, ...]:
    return lifecycle_decision(instance, LifecycleAction.DELETE).blockers


def can_deactivate(instance: Any) -> bool:
    return lifecycle_decision(instance, LifecycleAction.DEACTIVATE).allowed


def archive_reason_required(instance: Any) -> bool:
    policy = get_lifecycle_policy(instance)
    return LifecycleAction.ARCHIVE in policy.reason_required_actions


def record_lifecycle_action(
    *,
    instance: Any,
    decision: LifecycleDecision,
    actor_membership,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str = "",
    request: HttpRequest | None = None,
    audit_action: str | None = None,
    object_id: object | None = None,
    object_label: str | None = None,
    metadata: Mapping[str, Any] | None = None,
):
    """Write the standardized append-only audit event for a completed lifecycle action."""

    policy = get_lifecycle_policy(instance)
    company = getattr(instance, "company", None) or actor_membership.company
    event_metadata: dict[str, Any] = {
        "lifecycle_action": decision.action.value,
        "lifecycle_policy": decision.policy_name,
        "reason": (reason or "").strip(),
        "dependency_counts": dict(decision.evidence),
    }
    event_metadata.update(dict(metadata or {}))
    return record_audit_event(
        company=company,
        area=policy.area,
        action=audit_action or f"lifecycle.{decision.action.value}",
        object_type=policy.object_type,
        object_id=object_id if object_id is not None else getattr(instance, "pk"),
        object_label=object_label if object_label is not None else policy.label(instance),
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=event_metadata,
        request=request,
    )
