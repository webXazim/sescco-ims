"""U08 confidential contract/variation/remaining-cost approvals and forecasting.

Separate from Payroll/Inventory. Only explicitly authorized profiles may read any
financial values; every write is project-scoped and transactionally checked.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .budget_services import budget_rollups
from .models import PulseContractRevision, PulseContractVariation, PulseCostForecast

ZERO = Decimal("0.00")
MONEY_MAX = Decimal("999999999999.99")


def _money(value, *, signed=False, nonzero=False):
    try:
        amount = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError("Enter a valid amount in SAR.")
    if not amount.is_finite() or amount.as_tuple().exponent < -2 or abs(amount) > MONEY_MAX:
        raise ValidationError("Enter a valid SAR amount with two decimals, below SAR 1 trillion.")
    if not signed and amount < 0:
        raise ValidationError("This amount cannot be negative.")
    if nonzero and amount == ZERO:
        raise ValidationError("Variation must not be zero.")
    return amount


def _text(value, limit=500):
    value = " ".join((value or "").split())
    if not value or len(value) > limit:
        raise ValidationError(f"A reason is required (up to {limit} characters).")
    return value


def _authorized(actor, project_id, permission, *, writable=False):
    required = (AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
                AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW,
                AccessPermission.PULSE_BUDGETS_VIEW, AccessPermission.PULSE_FINANCIALS_VIEW, permission)
    if not all(membership_has_permission(actor, p) for p in required):
        raise PermissionDenied("Project contract, forecast and profit information is restricted.")
    projects = Project.objects.filter(pk=project_id, company_id=actor.company_id, deleted_at__isnull=True)
    if writable:
        projects = projects.select_for_update()
    project = get_object_or_404(projects)
    if not membership_allows_project(actor, project):
        raise PermissionDenied("This project is outside your access scope.")
    if writable and (project.status != Project.Status.ACTIVE or project.archived_at):
        raise ValidationError("Commercial entries require an active project.")
    return project


def _audit(project, actor, action, obj, request=None):
    # General Audit viewers must never learn commercial amount, reasons or margins.
    record_audit_event(company=project.company, area=AuditArea.PROJECTS, action=action,
        object_type=f"project_pulse.{type(obj).__name__}", object_id=obj.pk,
        object_label=f"{project.code} · Restricted commercial record {obj.pk}",
        actor_membership=actor, before={}, after={}, metadata={}, request=request)


def _approve(actor, obj, approve, note):
    if obj.status != obj.Status.PENDING:
        raise ValidationError("This proposal has already been reviewed.")
    if actor.pk == obj.submitted_by_id and actor.role != AccessRole.OWNER:
        raise PermissionDenied("Non-owners cannot approve their own submissions.")
    note = " ".join((note or "").split())
    if len(note) > 500 or (not approve and not note):
        raise ValidationError("Rejection requires a reason; notes must be within 500 characters.")
    obj.status = obj.Status.APPROVED if approve else obj.Status.REJECTED
    obj.reviewed_by = actor
    obj.reviewed_at = timezone.now()
    obj.review_note = note
    obj.save()
    return obj


def _current(model, project):
    return (model.objects.filter(project=project, status=model.Status.APPROVED)
            .order_by("-reviewed_at", "-pk").first())


def _variations_total(project):
    return (PulseContractVariation.objects.filter(project=project,
             status=PulseContractVariation.Status.APPROVED).aggregate(total=Sum("amount"))["total"] or ZERO)


@transaction.atomic
def propose_contract(*, actor, project_id, amount, reason, request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_CONTRACTS_MANAGE, writable=True)
    amount = _money(amount)
    reason = _text(reason)
    if PulseContractRevision.objects.filter(project=project, status="pending").exists():
        raise ValidationError("Review the existing pending contract proposal first.")
    if amount + _variations_total(project) < ZERO:
        raise ValidationError("Base contract plus approved variations cannot become negative.")
    obj = PulseContractRevision.objects.create(project=project, amount=amount, reason=reason, submitted_by=actor)
    _audit(project, actor, "pulse.contract.proposed", obj, request)
    return obj


@transaction.atomic
def review_contract(*, actor, project_id, record_id, approve, note="", request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_CONTRACTS_APPROVE, writable=True)
    obj = get_object_or_404(PulseContractRevision.objects.select_for_update(), project=project, pk=record_id)
    if approve and obj.amount + _variations_total(project) < ZERO:
        raise ValidationError("Approved variations would make the revised contract negative.")
    _approve(actor, obj, approve, note)
    _audit(project, actor, "pulse.contract.approved" if approve else "pulse.contract.rejected", obj, request)
    return obj


@transaction.atomic
def propose_variation(*, actor, project_id, amount, description, reference="", reason, request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_CONTRACTS_MANAGE, writable=True)
    amount = _money(amount, signed=True, nonzero=True)
    description = _text(description, 220)
    reason = _text(reason)
    reference = (reference or "").strip()
    if len(reference) > 100:
        raise ValidationError("Reference must be within 100 characters.")
    obj = PulseContractVariation.objects.create(project=project, amount=amount, description=description,
        reference=reference, reason=reason, submitted_by=actor)
    _audit(project, actor, "pulse.variation.proposed", obj, request)
    return obj


@transaction.atomic
def review_variation(*, actor, project_id, record_id, approve, note="", request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_CONTRACTS_APPROVE, writable=True)
    obj = get_object_or_404(PulseContractVariation.objects.select_for_update(), project=project, pk=record_id)
    base = _current(PulseContractRevision, project)
    if approve and base is None:
        raise ValidationError("Approve a base contract before approving variations.")
    if approve and base.amount + _variations_total(project) + obj.amount < ZERO:
        raise ValidationError("Contract variations cannot reduce revised contract value below zero.")
    _approve(actor, obj, approve, note)
    _audit(project, actor, "pulse.variation.approved" if approve else "pulse.variation.rejected", obj, request)
    return obj


@transaction.atomic
def propose_forecast(*, actor, project_id, remaining_cost, as_of_date, reason, request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_FORECASTS_MANAGE, writable=True)
    amount = _money(remaining_cost)
    reason = _text(reason)
    if not as_of_date:
        raise ValidationError("Forecast as-of date is required.")
    if PulseCostForecast.objects.filter(project=project, status="pending").exists():
        raise ValidationError("Review the existing pending forecast first.")
    obj = PulseCostForecast.objects.create(project=project, amount=amount, as_of_date=as_of_date,
        reason=reason, submitted_by=actor)
    _audit(project, actor, "pulse.forecast.proposed", obj, request)
    return obj


@transaction.atomic
def review_forecast(*, actor, project_id, record_id, approve, note="", request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_FORECASTS_APPROVE, writable=True)
    obj = get_object_or_404(PulseCostForecast.objects.select_for_update(), project=project, pk=record_id)
    if approve:
        obj.actual_cost_basis = budget_rollups(project)["approved_cost_total"]
    _approve(actor, obj, approve, note)
    _audit(project, actor, "pulse.forecast.approved" if approve else "pulse.forecast.rejected", obj, request)
    return obj


def commercial_summary(project):
    """Call ONLY after enforcing financial-view access in the view/service consumer.

    No fabricated revenue/profit when base contract or approved EAC is missing.
    A remaining-cost forecast is point-in-time; all later approved expense costs
    are included in actuals so the forecast should be refreshed regularly.
    """
    base = _current(PulseContractRevision, project)
    variation_total = _variations_total(project)
    forecast = _current(PulseCostForecast, project)
    budget = budget_rollups(project)
    approved_actual = budget["approved_cost_total"]
    revised_value = base.amount + variation_total if base else None
    final_cost = forecast.actual_cost_basis + forecast.amount if forecast and forecast.actual_cost_basis is not None else None
    contract_changed_since_forecast = bool(forecast and (
        (base and base.reviewed_at > forecast.reviewed_at) or
        PulseContractVariation.objects.filter(project=project, status="approved",
                                               reviewed_at__gt=forecast.reviewed_at).exists()
    ))
    forecast_stale = bool(forecast and (
        forecast.actual_cost_basis != approved_actual or contract_changed_since_forecast
    ))
    final_profit = revised_value - final_cost if revised_value is not None and final_cost is not None else None
    margin = ((final_profit / revised_value) * Decimal("100")).quantize(Decimal("0.01")) if final_profit is not None and revised_value else None
    planned_profit = (revised_value - budget["approved_budget_total"]
                      if revised_value is not None and budget["is_complete"] else None)
    return {
        "base": base, "forecast": forecast, "original_value": base.amount if base else None,
        "variations_total": variation_total, "revised_contract_value": revised_value,
        "approved_cost": approved_actual, "remaining_cost_estimate": forecast.amount if forecast else None,
        "estimated_final_cost": final_cost, "forecast_final_profit": final_profit,
        "forecast_stale": forecast_stale, "contract_changed_since_forecast": contract_changed_since_forecast,
        "forecast_actual_basis": forecast.actual_cost_basis if forecast else None,
        "forecast_margin_percent": margin, "planned_profit": planned_profit,
        "budget_is_complete": budget["is_complete"], "approved_budget": budget["approved_budget_total"],
        "contract_pending": PulseContractRevision.objects.filter(project=project, status="pending").first(),
        "forecast_pending": PulseCostForecast.objects.filter(project=project, status="pending").first(),
    }
