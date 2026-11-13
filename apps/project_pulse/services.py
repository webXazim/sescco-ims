"""Atomic, scoped Project Pulse team changes with immutable audit events."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.accounts.models import CompanyMembership
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .models import PulseProjectTeamMember


def can_manage_team(membership):
    return membership_has_permission(membership, AccessPermission.PULSE_TEAM_MANAGE)


def _editable_project(*, project_id, actor):
    project = get_object_or_404(
        Project.objects.select_for_update().filter(
            pk=project_id, company_id=actor.company_id, deleted_at__isnull=True
        )
    )
    if not membership_allows_project(actor, project):
        raise PermissionDenied("Project is not within your company project scope.")
    if project.status in (Project.Status.ARCHIVED, Project.Status.COMPLETED):
        raise ValidationError("Team assignments cannot be changed for archived or completed projects.")
    return project


def _require_manage(actor):
    if not all(membership_has_permission(actor, p) for p in (
        AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
        AccessPermission.PULSE_TEAM_VIEW, AccessPermission.PULSE_TEAM_MANAGE,
    )):
        raise PermissionDenied("Project Pulse team management authority is required.")


def _snapshot(record):
    if not record:
        return None
    return {"membership_id": str(record.membership_id), "user_id": record.membership.user_id,
            "role": record.role, "active": record.is_active}


@transaction.atomic
def assign_team_member(*, actor, project_id, member_id, role, request=None):
    _require_manage(actor)
    project = _editable_project(project_id=project_id, actor=actor)
    if role not in (PulseProjectTeamMember.Role.MANAGER, PulseProjectTeamMember.Role.MEMBER):
        raise ValidationError({"role": "Choose a valid team role."})
    try:
        member = CompanyMembership.objects.select_for_update().select_related(
            "user", "company", "access_profile"
        ).prefetch_related("access_profile__permission_grants").get(
            pk=member_id, company_id=project.company_id, is_active=True, user__is_active=True,
        )
    except (CompanyMembership.DoesNotExist, ValueError, TypeError, ValidationError) as exc:
        raise ValidationError({"membership": "Choose an active user from this company."}) from exc
    if not all(membership_has_permission(member, perm) for perm in (
        AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
    )) or not membership_allows_project(member, project):
        raise ValidationError({"membership": "User needs Project Pulse access to this project through their access profile and project scope."})

    record = PulseProjectTeamMember.objects.select_for_update().filter(
        project=project, membership=member,
    ).first()
    before = _snapshot(record)
    replaced_manager = None
    if role == PulseProjectTeamMember.Role.MANAGER:
        old_manager = PulseProjectTeamMember.objects.filter(
            project=project, role=PulseProjectTeamMember.Role.MANAGER, is_active=True
        ).exclude(membership=member).first()
        if old_manager:
            replaced_manager = str(old_manager.membership_id)
        # Serialize concurrent manager changes on the locked project. Demote first
        # so the database's unique-active-manager constraint is never violated.
        PulseProjectTeamMember.objects.filter(
            project=project, role=PulseProjectTeamMember.Role.MANAGER, is_active=True
        ).exclude(membership=member).update(role=PulseProjectTeamMember.Role.MEMBER)

    if record:
        record.role = role
        if not record.is_active:
            record.assigned_at = timezone.now()
        record.is_active = True
        record.ended_at = None
        record.assigned_by = actor
        record.save()
        action = "pulse.team.updated"
    else:
        record = PulseProjectTeamMember.objects.create(
            project=project, membership=member, role=role, assigned_by=actor,
        )
        action = "pulse.team.assigned"

    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action=action,
        object_type="project_pulse.PulseProjectTeamMember", object_id=record.pk,
        object_label=f"{project.code} · {member.user.display_name}",
        actor_membership=actor, before=before or {}, after=_snapshot(record),
        metadata={"replaced_manager_membership": replaced_manager} if replaced_manager else {},
        request=request,
    )
    return record


@transaction.atomic
def remove_team_member(*, actor, project_id, team_member_id, request=None):
    _require_manage(actor)
    project = _editable_project(project_id=project_id, actor=actor)
    record = get_object_or_404(
        PulseProjectTeamMember.objects.select_for_update().select_related("membership__user"),
        pk=team_member_id, project=project, is_active=True,
    )
    before = _snapshot(record)
    record.is_active = False
    record.ended_at = timezone.now()
    record.assigned_by = actor
    record.save()
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action="pulse.team.unassigned",
        object_type="project_pulse.PulseProjectTeamMember", object_id=record.pk,
        object_label=f"{project.code} · {record.membership.user.display_name}",
        actor_membership=actor, before=before, after=_snapshot(record), request=request,
    )
    return record
