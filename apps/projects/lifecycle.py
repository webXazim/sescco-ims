from __future__ import annotations

from typing import Mapping

from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.lifecycle import (
    LifecycleAction,
    LifecycleBlocker,
    LifecyclePolicy,
    register_lifecycle_policy,
)
from apps.projects.models import Project


class ProjectLifecyclePolicy(LifecyclePolicy):
    """Master-data lifecycle for the shared Inventory / Rental project authority.

    Operational states (active, on hold, completed) remain project-domain workflow states.
    Archive and Delete-unused are master-data lifecycle actions and therefore pass through
    the cross-module lifecycle authority.
    """

    area = AuditArea.PROJECTS
    object_type = "projects.Project"
    supported_actions = frozenset(
        {LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE}
    )
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DELETE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: Project) -> str:
        return instance.code

    def dependency_evidence(self, instance: Project, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.ARCHIVE:
            open_assignments = 0
            if hasattr(instance, "rental_assignments"):
                today = timezone.localdate()
                open_assignments = instance.rental_assignments.filter(
                    cancelled_at__isnull=True,
                ).filter(
                    Q(effective_to__isnull=True) | Q(effective_to__gte=today)
                ).count()
            return {
                "quantity_bearing_stock": instance.stock_items.filter(current_quantity__gt=0).count(),
                "open_rental_assignments": open_assignments,
            }
        if action is LifecycleAction.DELETE:
            open_assignments = 0
            if hasattr(instance, "rental_assignments"):
                today = timezone.localdate()
                open_assignments = instance.rental_assignments.filter(cancelled_at__isnull=True).filter(
                    Q(effective_to__isnull=True) | Q(effective_to__gte=today)
                ).count()
            return {
                "quantity_bearing_stock": instance.stock_items.filter(current_quantity__gt=0).count(),
                "open_rental_assignments": open_assignments,
            }
        return {}

    def blockers(self, instance: Project, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.status == Project.Status.ARCHIVED or instance.archived_at:
                return (
                    LifecycleBlocker(
                        code="already_archived",
                        field="project",
                        message="This project is already archived.",
                    ),
                )
            if evidence.get("quantity_bearing_stock", 0):
                return (
                    LifecycleBlocker(
                        code="stock_balance_exists",
                        field="project",
                        label="Stock records with balance",
                        count=evidence["quantity_bearing_stock"],
                        message="Transfer, use, or adjust all project stock to zero before archiving the project.",
                    ),
                )
            if evidence.get("open_rental_assignments", 0):
                return (
                    LifecycleBlocker(
                        code="open_rental_assignments",
                        field="project",
                        label="Open rental assignments",
                        count=evidence["open_rental_assignments"],
                        message="Release or transfer open Rental Manpower assignments before archiving the project.",
                    ),
                )
            return ()
        if action is LifecycleAction.RESTORE:
            if instance.status != Project.Status.ARCHIVED and not instance.archived_at:
                return (
                    LifecycleBlocker(
                        code="not_archived",
                        field="project",
                        message="This project is not archived.",
                    ),
                )
            return ()
        if action is LifecycleAction.DELETE:
            if evidence.get("quantity_bearing_stock", 0):
                return (LifecycleBlocker(
                    code="stock_balance_exists", field="project", label="Stock records with balance",
                    count=evidence["quantity_bearing_stock"],
                    message="Transfer, use, or adjust all project stock to zero before moving the project to Trash.",
                ),)
            if evidence.get("open_rental_assignments", 0):
                return (LifecycleBlocker(
                    code="open_rental_assignments", field="project", label="Open rental assignments",
                    count=evidence["open_rental_assignments"],
                    message="Release or transfer open Rental Manpower assignments before moving the project to Trash.",
                ),)
            return ()
        return ()


register_lifecycle_policy(Project, ProjectLifecyclePolicy())
