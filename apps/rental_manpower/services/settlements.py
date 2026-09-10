from __future__ import annotations

from apps.rental_manpower.project_adapter import project_public_id, rental_project_for_company

import hashlib
import json
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalAdjustment,
    RentalAdjustmentEffect,
    RentalAdjustmentStatus,
    RentalAdjustmentType,
    RentalRateType,
    RentalSettlementStatus,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    RentalWorker,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierPaymentMethod,
    SupplierPaymentStatus,
    SupplierSettlement,
    SupplierSettlementAdjustmentLine,
    SupplierSettlementLine,
    SupplierSettlementRateLine,
    WorkerAssignment,
    rental_adjustment_effect,
)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ACTIVE_PAYMENT_STATUSES = {SupplierPaymentStatus.PROCESSING, SupplierPaymentStatus.PAID}
PAYABLE_SETTLEMENT_STATUSES = {
    RentalSettlementStatus.APPROVED,
    RentalSettlementStatus.PAYMENT_PROCESSING,
    RentalSettlementStatus.PARTIALLY_PAID,
    RentalSettlementStatus.PAID,
    RentalSettlementStatus.CLOSED,
}


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite number."}) from exc
    return result


def _month_bounds(period_start: date) -> tuple[date, date]:
    start = period_start.replace(day=1)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


def _edit(membership) -> None:
    if not membership_can_edit(membership, Workspace.RENTAL):
        raise PermissionDenied("Your role cannot edit rental settlements.")


def _approve(membership) -> None:
    if not membership_can_workspace(membership, Workspace.RENTAL) or not membership_has_capability(membership, Capability.APPROVE):
        raise PermissionDenied("Your role cannot approve rental settlements.")


def _pay(membership) -> None:
    if not membership_can_workspace(membership, Workspace.RENTAL) or not membership_has_capability(membership, Capability.PAY):
        raise PermissionDenied("Your role cannot record supplier payments.")


def _assignment_on_date(*, company, worker_id, project_id, when: date) -> WorkerAssignment:
    assignment = (
        WorkerAssignment.objects.select_for_update()
        .for_company(company)
        .select_related("worker", "worker__supplier", "project")
        .filter(worker_id=worker_id, project_id=project_id, cancelled_at__isnull=True, effective_from__lte=when)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=when))
        .order_by("-effective_from", "-created_at")
        .first()
    )
    if assignment is None:
        raise ValidationError({"transaction_date": "Worker has no effective assignment to this project on the transaction date."})
    return assignment


def _adjustment_snapshot(assignment: WorkerAssignment) -> dict[str, object]:
    return {
        "supplier": assignment.worker.supplier,
        "supplier_code": assignment.worker.supplier.code,
        "supplier_name": assignment.worker.supplier.name,
        "project_code": assignment.project.code,
        "project_name": assignment.project.name,
        "worker_number": assignment.worker.worker_number,
        "worker_name": assignment.worker.full_name,
        "trade": assignment.trade,
        "rate_type": assignment.rate_type,
        "rate": assignment.rate,
    }


@transaction.atomic
def create_rental_adjustment(
    *, actor_membership, worker_id, project_id, transaction_date: date, period_start: date,
    adjustment_type: str, amount: Decimal, reason: str, reference: str = "", request=None,
) -> RentalAdjustment:
    _edit(actor_membership)
    company = actor_membership.company
    start, _end = _month_bounds(period_start)
    if transaction_date.year != start.year or transaction_date.month != start.month:
        raise ValidationError({"transaction_date": "Transaction date must fall inside the selected settlement month."})
    if adjustment_type not in {value for value, _label in RentalAdjustmentType.choices}:
        raise ValidationError({"adjustment_type": "Select a valid rental adjustment type."})
    amount = _decimal(amount, "amount")
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "A clear adjustment reason is required."})
    worker = RentalWorker.objects.select_for_update().for_company(company).select_related("supplier").get(pk=worker_id)
    project = rental_project_for_company(company=company, identifier=project_id, for_update=True)
    assignment = _assignment_on_date(company=company, worker_id=worker.pk, project_id=project.pk, when=transaction_date)
    snap = _adjustment_snapshot(assignment)
    adjustment = RentalAdjustment(
        company=company,
        worker=worker,
        project=project,
        assignment=assignment,
        transaction_date=transaction_date,
        period_start=start,
        adjustment_type=adjustment_type,
        amount=_money(amount),
        reason=reason,
        reference=(reference or "").strip().upper(),
        **snap,
    )
    adjustment.full_clean()
    adjustment.save()
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action="rental.adjustment.created",
        object_type="rental_manpower.RentalAdjustment", object_id=adjustment.pk,
        object_label=f"{worker.worker_number} · {adjustment.get_adjustment_type_display()}",
        actor_membership=actor_membership,
        after={"status": adjustment.status, "type": adjustment.adjustment_type, "amount": str(adjustment.amount)},
        metadata={"project_id": project_public_id(project), "period": f"{start:%Y-%m}"}, request=request,
    )
    return adjustment


@transaction.atomic
def update_rental_adjustment(*, actor_membership, adjustment_id, request=None, **changes) -> RentalAdjustment:
    _edit(actor_membership)
    company = actor_membership.company
    adjustment = RentalAdjustment.objects.select_for_update().for_company(company).select_related("worker", "supplier", "project", "assignment").get(pk=adjustment_id)
    if adjustment.status != RentalAdjustmentStatus.DRAFT:
        raise ValidationError("Only Draft rental adjustments can be edited.")
    before = {"amount": str(adjustment.amount), "reason": adjustment.reason, "reference": adjustment.reference, "type": adjustment.adjustment_type}
    allowed = {"adjustment_type", "amount", "reason", "reference"}
    for field, value in changes.items():
        if field not in allowed:
            continue
        if field == "amount":
            value = _money(_decimal(value, "amount"))
        if field == "adjustment_type" and value not in {v for v, _ in RentalAdjustmentType.choices}:
            raise ValidationError({"adjustment_type": "Select a valid rental adjustment type."})
        setattr(adjustment, field, value)
    adjustment.full_clean()
    adjustment.save()
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action="rental.adjustment.updated",
        object_type="rental_manpower.RentalAdjustment", object_id=adjustment.pk,
        object_label=f"{adjustment.worker_number} · {adjustment.get_adjustment_type_display()}",
        actor_membership=actor_membership, before=before,
        after={"amount": str(adjustment.amount), "reason": adjustment.reason, "reference": adjustment.reference, "type": adjustment.adjustment_type},
        request=request,
    )
    return adjustment


@transaction.atomic
def transition_rental_adjustment(*, actor_membership, adjustment_id, action: str, reason: str = "", request=None) -> RentalAdjustment:
    company = actor_membership.company
    adjustment = RentalAdjustment.objects.select_for_update().for_company(company).select_related("worker", "supplier", "project").get(pk=adjustment_id)
    action = (action or "").strip().lower().replace("-", "_")
    before = adjustment.status
    now = timezone.now()
    if action == "submit":
        _edit(actor_membership)
        if adjustment.status != RentalAdjustmentStatus.DRAFT:
            raise ValidationError("Only Draft rental adjustments can be submitted.")
        adjustment.status = RentalAdjustmentStatus.REVIEW
        adjustment.submitted_at = now
        adjustment.submitted_by = actor_membership.user
    elif action == "approve":
        _approve(actor_membership)
        if adjustment.status != RentalAdjustmentStatus.REVIEW:
            raise ValidationError("Only Review rental adjustments can be approved.")
        locked_settlement = (
            SupplierSettlement.objects.select_for_update().for_company(company)
            .filter(project=adjustment.project, supplier=adjustment.supplier, period_start=adjustment.period_start)
            .filter(status__in=[
                RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING,
                RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAID, RentalSettlementStatus.CLOSED,
            ]).first()
        )
        if locked_settlement:
            raise ValidationError("This supplier settlement is already approved. The adjustment cannot be added to that closed financial snapshot.")
        adjustment.status = RentalAdjustmentStatus.APPROVED
        adjustment.approved_at = now
        adjustment.approved_by = actor_membership.user
    elif action == "return":
        _approve(actor_membership)
        if adjustment.status != RentalAdjustmentStatus.REVIEW:
            raise ValidationError("Only Review rental adjustments can be returned to Draft.")
        if not (reason or "").strip():
            raise ValidationError({"reason": "A correction reason is required."})
        adjustment.status = RentalAdjustmentStatus.DRAFT
        adjustment.submitted_at = None
        adjustment.submitted_by = None
    else:
        raise ValidationError({"action": "Action must be submit, approve, or return."})
    adjustment.save()
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action=f"rental.adjustment.{action}",
        object_type="rental_manpower.RentalAdjustment", object_id=adjustment.pk,
        object_label=f"{adjustment.worker_number} · {adjustment.get_adjustment_type_display()}",
        actor_membership=actor_membership, before={"status": before}, after={"status": adjustment.status},
        metadata={"reason": (reason or "").strip()}, request=request,
    )
    return adjustment


def _canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source_payload(*, period: RentalTimesheetPeriod, supplier: ManpowerSupplier) -> dict[str, object]:
    entries = list(
        RentalTimesheetEntry.objects.for_company(period.company)
        .filter(period=period, worker__supplier=supplier)
        .order_by("worker__worker_number", "work_date", "assignment_id")
        .values(
            "worker_id", "worker__worker_number", "assignment_id", "work_date", "regular_hours", "code",
            "supplier_code", "supplier_name", "project_code", "project_name", "trade", "rate_type", "rate",
        )
    )
    overtime = list(
        RentalTimesheetOvertime.objects.for_company(period.company)
        .filter(period=period, worker__supplier=supplier)
        .order_by("worker__worker_number", "assignment_id")
        .values("worker_id", "worker__worker_number", "assignment_id", "hours", "rate", "trade", "rate_type", "supplier_code", "supplier_name", "project_code", "project_name")
    )
    adjustments = list(
        RentalAdjustment.objects.for_company(period.company)
        .filter(period_start=period.period_start, project=period.project, supplier=supplier, status=RentalAdjustmentStatus.APPROVED)
        .order_by("worker__worker_number", "transaction_date", "created_at")
        .values("id", "worker_id", "worker_number", "transaction_date", "adjustment_type", "amount", "reason", "reference", "supplier_code", "project_code", "trade", "rate_type", "rate")
    )
    return {
        "timesheet": {"id": str(period.pk), "revision": period.revision, "status": period.status, "project": project_public_id(period.project), "period": str(period.period_start)},
        "supplier": {"id": str(supplier.pk), "code": supplier.code},
        "entries": entries,
        "overtime": overtime,
        "adjustments": adjustments,
    }


def settlement_source_fingerprint(*, period: RentalTimesheetPeriod, supplier: ManpowerSupplier) -> str:
    return _canonical_hash(_source_payload(period=period, supplier=supplier))


def _snapshot_payload(settlement: SupplierSettlement) -> dict[str, object]:
    lines = []
    for line in (
        SupplierSettlementLine.objects.for_company(settlement.company)
        .filter(settlement=settlement).order_by("worker_number", "worker_id")
    ):
        rates = list(
            SupplierSettlementRateLine.objects.for_company(settlement.company)
            .filter(settlement_line=line).order_by("effective_from", "assignment_id")
            .values("assignment_id", "effective_from", "effective_to", "trade", "rate_type", "rate", "regular_hours", "billable_days", "calendar_days", "base_amount")
        )
        adjustments = list(
            SupplierSettlementAdjustmentLine.objects.for_company(settlement.company)
            .filter(settlement_line=line).order_by("transaction_date", "adjustment_id")
            .values("adjustment_id", "adjustment_type", "adjustment_label", "effect", "amount", "reason", "reference", "transaction_date")
        )
        lines.append({
            "worker_id": str(line.worker_id), "worker_number": line.worker_number, "worker_name": line.worker_name,
            "supplier_code": line.supplier_code, "supplier_name": line.supplier_name,
            "project_code": line.project_code, "project_name": line.project_name,
            "trade_summary": line.trade_summary, "rate_summary": line.rate_summary,
            "regular_hours": str(line.regular_hours), "work_days": line.work_days,
            "overtime_hours": str(line.overtime_hours), "base_amount": str(line.base_amount),
            "overtime_amount": str(line.overtime_amount), "gross_amount": str(line.gross_amount),
            "adjustment_earnings": str(line.adjustment_earnings), "adjustment_deductions": str(line.adjustment_deductions),
            "net_amount": str(line.net_amount), "rates": rates, "adjustments": adjustments,
        })
    return {
        "settlement_number": settlement.settlement_number,
        "period_start": str(settlement.period_start), "period_end": str(settlement.period_end),
        "project_id": project_public_id(settlement.project), "supplier_id": str(settlement.supplier_id),
        "source_timesheet_id": str(settlement.source_timesheet_id), "source_timesheet_revision": settlement.source_timesheet_revision,
        "project_code": settlement.project_code, "project_name": settlement.project_name,
        "supplier_code": settlement.supplier_code, "supplier_name": settlement.supplier_name,
        "calculation_version": settlement.calculation_version,
        "totals": {
            "worker_count": settlement.worker_count, "regular_hours": str(settlement.total_regular_hours),
            "work_days": settlement.total_work_days, "overtime_hours": str(settlement.total_overtime_hours),
            "base": str(settlement.total_base), "overtime": str(settlement.total_overtime),
            "gross": str(settlement.total_gross), "adjustment_earnings": str(settlement.total_adjustment_earnings),
            "adjustment_deductions": str(settlement.total_adjustment_deductions), "net": str(settlement.total_net),
        },
        "lines": lines,
    }


def settlement_snapshot_fingerprint(settlement: SupplierSettlement) -> str:
    return _canonical_hash(_snapshot_payload(settlement))


def _assert_settlement_integrity(settlement: SupplierSettlement) -> None:
    if settlement.source_timesheet.status != RentalTimesheetStatus.LOCKED:
        raise ValidationError("The source rental timesheet is no longer Locked.")
    current_source = settlement_source_fingerprint(period=settlement.source_timesheet, supplier=settlement.supplier)
    if not settlement.source_fingerprint or current_source != settlement.source_fingerprint:
        raise ValidationError("Settlement source data changed after calculation. Recalculate before continuing.")
    current_snapshot = settlement_snapshot_fingerprint(settlement)
    if not settlement.snapshot_fingerprint or current_snapshot != settlement.snapshot_fingerprint:
        raise ValidationError("Settlement snapshot integrity check failed. Recalculate before continuing.")


def _delete_snapshot(settlement: SupplierSettlement) -> None:
    SupplierSettlementAdjustmentLine.objects.filter(company=settlement.company, settlement_line__settlement=settlement).delete()
    SupplierSettlementRateLine.objects.filter(company=settlement.company, settlement_line__settlement=settlement).delete()
    SupplierSettlementLine.objects.filter(company=settlement.company, settlement=settlement).delete()


def _supplier_ids_for_period(period: RentalTimesheetPeriod) -> list[Any]:
    ids = set(RentalTimesheetEntry.objects.filter(period=period).values_list("worker__supplier_id", flat=True))
    ids.update(RentalTimesheetOvertime.objects.filter(period=period).values_list("worker__supplier_id", flat=True))
    return sorted(ids, key=str)


def _calculate_supplier_snapshot(*, settlement: SupplierSettlement) -> None:
    company = settlement.company
    period = settlement.source_timesheet
    supplier = settlement.supplier
    entries = list(
        RentalTimesheetEntry.objects.for_company(company).filter(period=period, worker__supplier=supplier)
        .select_related("worker", "worker__supplier", "assignment").order_by("worker__worker_number", "work_date")
    )
    if not entries:
        raise ValidationError(f"No locked timesheet rows exist for supplier {supplier.name}.")
    overtime = list(
        RentalTimesheetOvertime.objects.for_company(company).filter(period=period, worker__supplier=supplier)
        .select_related("worker", "assignment").order_by("worker__worker_number")
    )
    adjustments = list(
        RentalAdjustment.objects.select_for_update().for_company(company)
        .filter(period_start=period.period_start, project=period.project, supplier=supplier, status=RentalAdjustmentStatus.APPROVED)
        .select_related("worker", "assignment").order_by("worker__worker_number", "transaction_date", "created_at")
    )
    _delete_snapshot(settlement)
    by_worker: dict[Any, list[RentalTimesheetEntry]] = defaultdict(list)
    for entry in entries:
        by_worker[entry.worker_id].append(entry)
    ot_by_worker = {row.worker_id: row for row in overtime}
    adj_by_worker: dict[Any, list[RentalAdjustment]] = defaultdict(list)
    for adjustment in adjustments:
        adj_by_worker[adjustment.worker_id].append(adjustment)

    totals = defaultdict(lambda: Decimal("0"))
    total_days = 0
    month_days = Decimal(monthrange(period.period_start.year, period.period_start.month)[1])

    for worker_id, worker_entries in by_worker.items():
        worker = worker_entries[0].worker
        by_assignment: dict[Any, list[RentalTimesheetEntry]] = defaultdict(list)
        for entry in worker_entries:
            by_assignment[entry.assignment_id].append(entry)
        rate_calculations: list[dict[str, object]] = []
        base = ZERO
        work_days = 0
        regular_hours = sum((row.regular_hours for row in worker_entries), Decimal("0"))
        for assignment_id, segment_entries in by_assignment.items():
            first = segment_entries[0]
            rate = first.rate
            rate_type = first.rate_type
            segment_hours = sum((row.regular_hours for row in segment_entries), Decimal("0"))
            billable_days = sum(1 for row in segment_entries if row.regular_hours > 0)
            calendar_days = len({row.work_date for row in segment_entries})
            if rate_type == RentalRateType.HOURLY:
                segment_base = _money(segment_hours * rate)
            elif rate_type == RentalRateType.DAILY:
                segment_base = _money(Decimal(billable_days) * rate)
            elif rate_type == RentalRateType.MONTHLY:
                segment_base = _money(rate * Decimal(calendar_days) / month_days)
            else:
                raise ValidationError(f"Unsupported rental rate type: {rate_type}")
            base += segment_base
            work_days += billable_days
            rate_calculations.append({
                "assignment": first.assignment,
                "effective_from": min(row.work_date for row in segment_entries),
                "effective_to": max(row.work_date for row in segment_entries),
                "trade": first.trade,
                "rate_type": rate_type,
                "rate": rate,
                "regular_hours": segment_hours,
                "billable_days": billable_days,
                "calendar_days": calendar_days,
                "base_amount": segment_base,
            })
        base = _money(base)
        ot = ot_by_worker.get(worker_id)
        ot_hours = ot.hours if ot else Decimal("0")
        overtime_amount = _money(ot.hours * ot.rate) if ot else ZERO
        gross = _money(base + overtime_amount)
        earning = ZERO
        deduction = ZERO
        for adjustment in adj_by_worker.get(worker_id, []):
            if rental_adjustment_effect(adjustment.adjustment_type) == RentalAdjustmentEffect.EARNING:
                earning += adjustment.amount
            else:
                deduction += adjustment.amount
        earning, deduction = _money(earning), _money(deduction)
        net = _money(gross + earning - deduction)
        if net < 0:
            raise ValidationError({"adjustments": f"Approved adjustments make {worker.worker_number} {worker.full_name}'s supplier payable negative."})
        trades = []
        rate_labels = []
        for item in rate_calculations:
            if item["trade"] not in trades:
                trades.append(str(item["trade"]))
            label = f"{RentalRateType(item['rate_type']).label} {item['rate']}"
            if label not in rate_labels:
                rate_labels.append(label)
        line = SupplierSettlementLine(
            company=company, settlement=settlement, worker=worker,
            worker_number=worker.worker_number, worker_name=worker.full_name,
            supplier_code=settlement.supplier_code, supplier_name=settlement.supplier_name,
            project_code=settlement.project_code, project_name=settlement.project_name,
            trade_summary=" → ".join(trades), rate_summary=" · ".join(rate_labels),
            regular_hours=regular_hours, work_days=work_days, overtime_hours=ot_hours,
            base_amount=base, overtime_amount=overtime_amount, gross_amount=gross,
            adjustment_earnings=earning, adjustment_deductions=deduction, net_amount=net,
        )
        line.full_clean(); line.save()
        for item in rate_calculations:
            rate_line = SupplierSettlementRateLine(company=company, settlement_line=line, **item)
            rate_line.full_clean(); rate_line.save()
        for adjustment in adj_by_worker.get(worker_id, []):
            effect = rental_adjustment_effect(adjustment.adjustment_type)
            adj_line = SupplierSettlementAdjustmentLine(
                company=company, settlement_line=line, adjustment=adjustment,
                adjustment_type=adjustment.adjustment_type, adjustment_label=adjustment.get_adjustment_type_display(),
                effect=effect, amount=adjustment.amount, reason=adjustment.reason, reference=adjustment.reference,
                transaction_date=adjustment.transaction_date,
            )
            adj_line.full_clean(); adj_line.save()
        totals["regular_hours"] += regular_hours
        totals["overtime_hours"] += ot_hours
        totals["base"] += base
        totals["overtime"] += overtime_amount
        totals["gross"] += gross
        totals["earning"] += earning
        totals["deduction"] += deduction
        totals["net"] += net
        total_days += work_days

    settlement.worker_count = len(by_worker)
    settlement.total_regular_hours = totals["regular_hours"].quantize(CENT)
    settlement.total_work_days = total_days
    settlement.total_overtime_hours = totals["overtime_hours"].quantize(CENT)
    settlement.total_base = _money(totals["base"])
    settlement.total_overtime = _money(totals["overtime"])
    settlement.total_gross = _money(totals["gross"])
    settlement.total_adjustment_earnings = _money(totals["earning"])
    settlement.total_adjustment_deductions = _money(totals["deduction"])
    settlement.total_net = _money(totals["net"])
    settlement.full_clean()
    settlement.save()
    settlement.snapshot_fingerprint = settlement_snapshot_fingerprint(settlement)
    settlement.save(update_fields=("snapshot_fingerprint", "updated_at"))


@transaction.atomic
def calculate_project_settlements(*, actor_membership, project_id, period_start: date, request=None) -> list[SupplierSettlement]:
    _edit(actor_membership)
    company = actor_membership.company
    start, end = _month_bounds(period_start)
    project = rental_project_for_company(company=company, identifier=project_id, for_update=True)
    period = (
        RentalTimesheetPeriod.objects.select_for_update().for_company(company)
        .select_related("project").filter(project=project, period_start=start).first()
    )
    if period is None or period.status != RentalTimesheetStatus.LOCKED:
        raise ValidationError("A Locked rental timesheet is required before supplier settlement calculation.")
    supplier_ids = _supplier_ids_for_period(period)
    if not supplier_ids:
        raise ValidationError("The locked timesheet contains no supplier worker rows to settle.")
    suppliers = {supplier.pk: supplier for supplier in ManpowerSupplier.objects.select_for_update().for_company(company).filter(pk__in=supplier_ids)}
    existing = {
        obj.supplier_id: obj
        for obj in SupplierSettlement.objects.select_for_update().for_company(company).filter(project=project, period_start=start)
    }
    results: list[SupplierSettlement] = []
    now = timezone.now()
    for supplier_id in supplier_ids:
        supplier = suppliers.get(supplier_id)
        if supplier is None:
            raise ValidationError("A timesheet row references a supplier that is unavailable in this company.")
        settlement = existing.get(supplier_id)
        created = settlement is None
        if settlement is None:
            settlement = SupplierSettlement(
                company=company,
                settlement_number=allocate_number(company=company, key="rental.settlement", prefix="SET-", padding=6),
                period_start=start, period_end=end, project=project, supplier=supplier, source_timesheet=period,
                source_timesheet_revision=period.revision,
            )
        elif settlement.status not in {RentalSettlementStatus.DRAFT, RentalSettlementStatus.CALCULATED}:
            raise ValidationError(f"{settlement.settlement_number} is {settlement.get_status_display()} and cannot be recalculated.")
        settlement.source_timesheet = period
        settlement.source_timesheet_revision = period.revision
        settlement.project_code = project.code
        settlement.project_name = project.name
        settlement.supplier_code = supplier.code
        settlement.supplier_name = supplier.name
        settlement.status = RentalSettlementStatus.CALCULATED
        settlement.revision = settlement.revision + 1
        settlement.calculated_at = now
        settlement.calculated_by = actor_membership.user
        settlement.submitted_at = None
        settlement.submitted_by = None
        settlement.approved_at = None
        settlement.approved_by = None
        settlement.reviewer_note = ""
        settlement.source_fingerprint = settlement_source_fingerprint(period=period, supplier=supplier)
        settlement.snapshot_fingerprint = ""
        settlement.full_clean(); settlement.save()
        _calculate_supplier_snapshot(settlement=settlement)
        record_audit_event(
            company=company, area=AuditArea.RENTAL,
            action="rental.settlement.calculated" if created else "rental.settlement.recalculated",
            object_type="rental_manpower.SupplierSettlement", object_id=settlement.pk,
            object_label=settlement.settlement_number, actor_membership=actor_membership,
            after={"status": settlement.status, "net": str(settlement.total_net), "revision": settlement.revision},
            metadata={"project_id": project_public_id(project), "supplier_id": str(supplier.pk), "period": f"{start:%Y-%m}"}, request=request,
        )
        results.append(settlement)
    return results


@transaction.atomic
def transition_project_settlements(*, actor_membership, project_id, period_start: date, action: str, reason: str = "", confirmed: bool = False, request=None) -> list[SupplierSettlement]:
    company = actor_membership.company
    start, _end = _month_bounds(period_start)
    project = rental_project_for_company(company=company, identifier=project_id, for_update=True)
    rows = list(
        SupplierSettlement.objects.select_for_update().for_company(company)
        .select_related("source_timesheet", "supplier", "project")
        .filter(project=project, period_start=start).order_by("supplier_code")
    )
    if not rows:
        raise ValidationError("No calculated supplier settlements exist for this project and period.")
    action = (action or "").strip().lower().replace("-", "_")
    now = timezone.now()
    if action == "submit":
        _edit(actor_membership)
        eligible = [row for row in rows if row.status == RentalSettlementStatus.CALCULATED]
        if len(eligible) != len(rows):
            raise ValidationError("Every supplier settlement for this project must be Calculated before Finance Review.")
        for row in eligible:
            _assert_settlement_integrity(row)
            before = row.status
            row.status = RentalSettlementStatus.REVIEW
            row.submitted_at = now; row.submitted_by = actor_membership.user
            row.save()
            record_audit_event(company=company, area=AuditArea.RENTAL, action="rental.settlement.submitted", object_type="rental_manpower.SupplierSettlement", object_id=row.pk, object_label=row.settlement_number, actor_membership=actor_membership, before={"status": before}, after={"status": row.status}, request=request)
    elif action == "approve":
        _approve(actor_membership)
        if not confirmed:
            raise ValidationError({"confirmed": "Reviewer confirmation is required before approving supplier settlements."})
        eligible = [row for row in rows if row.status == RentalSettlementStatus.REVIEW]
        if len(eligible) != len(rows):
            raise ValidationError("Every supplier settlement for this project must be in Review before approval.")
        for row in eligible:
            _assert_settlement_integrity(row)
            before = row.status
            row.status = RentalSettlementStatus.PAID if row.total_net == ZERO else RentalSettlementStatus.APPROVED
            row.approved_at = now; row.approved_by = actor_membership.user
            row.reviewer_note = (reason or "").strip()
            row.save()
            record_audit_event(company=company, area=AuditArea.RENTAL, action="rental.settlement.approved", object_type="rental_manpower.SupplierSettlement", object_id=row.pk, object_label=row.settlement_number, actor_membership=actor_membership, before={"status": before}, after={"status": row.status}, metadata={"note": row.reviewer_note, "zero_payable": row.total_net == ZERO}, request=request)
    elif action == "return":
        _approve(actor_membership)
        if not (reason or "").strip():
            raise ValidationError({"reason": "A correction reason is required."})
        eligible = [row for row in rows if row.status == RentalSettlementStatus.REVIEW]
        if not eligible:
            raise ValidationError("Only settlements in Finance Review can be returned for changes.")
        for row in eligible:
            before = row.status
            row.status = RentalSettlementStatus.CALCULATED
            row.submitted_at = None; row.submitted_by = None
            row.reviewer_note = (reason or "").strip()
            row.save()
            record_audit_event(company=company, area=AuditArea.RENTAL, action="rental.settlement.returned", object_type="rental_manpower.SupplierSettlement", object_id=row.pk, object_label=row.settlement_number, actor_membership=actor_membership, before={"status": before}, after={"status": row.status}, metadata={"reason": row.reviewer_note}, request=request)
    elif action == "close":
        _pay(actor_membership)
        eligible = [row for row in rows if row.status == RentalSettlementStatus.PAID]
        if len(eligible) != len(rows):
            raise ValidationError("All supplier settlements must be fully Paid before this project settlement period can be closed.")
        for row in eligible:
            before = row.status
            row.status = RentalSettlementStatus.CLOSED
            row.closed_at = now; row.closed_by = actor_membership.user
            row.save()
            record_audit_event(company=company, area=AuditArea.RENTAL, action="rental.settlement.closed", object_type="rental_manpower.SupplierSettlement", object_id=row.pk, object_label=row.settlement_number, actor_membership=actor_membership, before={"status": before}, after={"status": row.status}, request=request)
    else:
        raise ValidationError({"action": "Action must be submit, approve, return, or close."})
    return rows


def _allocation_totals(settlement: SupplierSettlement) -> tuple[Decimal, Decimal]:
    rows = SupplierPaymentAllocation.objects.for_company(settlement.company).filter(settlement=settlement, payment__status__in=list(ACTIVE_PAYMENT_STATUSES)).values("payment__status").annotate(total=Sum("amount"))
    paid = ZERO; processing = ZERO
    for row in rows:
        if row["payment__status"] == SupplierPaymentStatus.PAID:
            paid += row["total"] or ZERO
        elif row["payment__status"] == SupplierPaymentStatus.PROCESSING:
            processing += row["total"] or ZERO
    return _money(paid), _money(processing)


def _sync_settlement_payment_status(*, settlement: SupplierSettlement, actor_membership=None, request=None, reason: str = "") -> SupplierSettlement:
    paid, processing = _allocation_totals(settlement)
    if paid >= settlement.total_net:
        target = RentalSettlementStatus.PAID
    elif paid > ZERO:
        target = RentalSettlementStatus.PARTIALLY_PAID
    elif processing > ZERO:
        target = RentalSettlementStatus.PAYMENT_PROCESSING
    else:
        target = RentalSettlementStatus.APPROVED
    before = settlement.status
    if before == RentalSettlementStatus.CLOSED and target == RentalSettlementStatus.PAID:
        return settlement
    if before != target:
        settlement.status = target
        if before == RentalSettlementStatus.CLOSED and target != RentalSettlementStatus.PAID:
            settlement.closed_at = None; settlement.closed_by = None
        settlement.save()
        if actor_membership:
            record_audit_event(
                company=settlement.company, area=AuditArea.RENTAL, action="rental.settlement.payment_status_changed",
                object_type="rental_manpower.SupplierSettlement", object_id=settlement.pk, object_label=settlement.settlement_number,
                actor_membership=actor_membership, before={"status": before}, after={"status": target},
                metadata={"paid": str(paid), "processing": str(processing), "reason": reason}, request=request,
            )
    return settlement


@transaction.atomic
def record_supplier_payment(
    *, actor_membership, settlement_id, payment_date: date, method: str, amount: Decimal,
    status: str = SupplierPaymentStatus.PROCESSING, transaction_reference: str = "", note: str = "", request=None,
) -> SupplierPayment:
    _pay(actor_membership)
    company = actor_membership.company
    settlement = SupplierSettlement.objects.select_for_update().for_company(company).select_related("supplier", "project").get(pk=settlement_id)
    if settlement.status not in PAYABLE_SETTLEMENT_STATUSES:
        raise ValidationError("Only an Approved supplier settlement can be paid.")
    if settlement.status == RentalSettlementStatus.CLOSED:
        raise ValidationError("Closed supplier settlements cannot receive new payments.")
    if settlement.approved_at and payment_date < timezone.localdate(settlement.approved_at):
        raise ValidationError({"payment_date": "Payment date cannot be earlier than the settlement approval date."})
    if status == SupplierPaymentStatus.PAID and payment_date > timezone.localdate():
        raise ValidationError({"payment_date": "A Paid supplier payment cannot use a future payment date."})
    amount = _money(_decimal(amount, "amount"))
    if amount <= ZERO:
        raise ValidationError({"amount": "Payment amount must be greater than zero."})
    paid, processing = _allocation_totals(settlement)
    available = _money(settlement.total_net - paid - processing)
    if amount > available:
        raise ValidationError({"amount": f"Payment exceeds the available supplier payable of {available}."})
    if status not in {SupplierPaymentStatus.PROCESSING, SupplierPaymentStatus.PAID}:
        raise ValidationError({"status": "A new supplier payment must start as Processing or Paid."})
    if method not in {value for value, _label in SupplierPaymentMethod.choices}:
        raise ValidationError({"method": "Select a valid supplier payment method."})
    payment = SupplierPayment(
        company=company, supplier=settlement.supplier,
        payment_number=allocate_number(company=company, key="rental.supplier_payment", prefix="SPAY-", padding=6),
        payment_date=payment_date, method=method, amount=amount, status=status,
        transaction_reference=(transaction_reference or "").strip().upper(), note=(note or "").strip(),
        supplier_code=settlement.supplier_code, supplier_name=settlement.supplier_name,
        paid_at=timezone.now() if status == SupplierPaymentStatus.PAID else None,
    )
    payment.full_clean(); payment.save()
    allocation = SupplierPaymentAllocation(company=company, payment=payment, settlement=settlement, amount=amount)
    allocation.full_clean(); allocation.save()
    _sync_settlement_payment_status(settlement=settlement, actor_membership=actor_membership, request=request)
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action="rental.supplier_payment.recorded",
        object_type="rental_manpower.SupplierPayment", object_id=payment.pk, object_label=payment.payment_number,
        actor_membership=actor_membership,
        after={"status": payment.status, "amount": str(payment.amount), "method": payment.method},
        metadata={"settlement_id": str(settlement.pk), "settlement_number": settlement.settlement_number}, request=request,
    )
    return payment


@transaction.atomic
def transition_supplier_payment(
    *, actor_membership, payment_id, status: str, transaction_reference: str = "", reason: str = "", request=None,
) -> SupplierPayment:
    _pay(actor_membership)
    company = actor_membership.company
    payment = SupplierPayment.objects.select_for_update().for_company(company).select_related("supplier").get(pk=payment_id)
    allocations = list(
        SupplierPaymentAllocation.objects.select_for_update().for_company(company)
        .filter(payment=payment).select_related("settlement")
    )
    settlements = [SupplierSettlement.objects.select_for_update().for_company(company).get(pk=row.settlement_id) for row in allocations]
    target = (status or "").strip().lower().replace(" ", "_")
    before = payment.status
    now = timezone.now()
    if before == SupplierPaymentStatus.PROCESSING:
        if target not in {SupplierPaymentStatus.PAID, SupplierPaymentStatus.FAILED, SupplierPaymentStatus.CANCELLED}:
            raise ValidationError("A Processing supplier payment can become Paid, Failed, or Cancelled.")
    elif before == SupplierPaymentStatus.PAID:
        if target != SupplierPaymentStatus.REVERSED:
            raise ValidationError("A Paid supplier payment can only be Reversed.")
    else:
        raise ValidationError("Failed, Reversed, and Cancelled payments are terminal. Create a retry instead of rewriting history.")
    ref = (transaction_reference or payment.transaction_reference or "").strip().upper()
    reason = (reason or "").strip()
    if target == SupplierPaymentStatus.PAID and payment.payment_date > timezone.localdate():
        raise ValidationError({"payment_date": "A Paid supplier payment cannot use a future payment date."})
    if target == SupplierPaymentStatus.PAID and payment.method != SupplierPaymentMethod.CASH and not ref:
        raise ValidationError({"transaction_reference": "A bank/cheque reference is required before marking the payment Paid."})
    if target in {SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED} and not reason:
        raise ValidationError({"reason": "A failure/reversal reason is required."})
    payment.status = target
    payment.transaction_reference = ref
    payment.result_reason = reason if target in {SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED} else ""
    if target == SupplierPaymentStatus.PAID:
        payment.paid_at = now
    elif target == SupplierPaymentStatus.REVERSED:
        payment.reversed_at = now
    elif target == SupplierPaymentStatus.CANCELLED:
        payment.cancelled_at = now
    payment.full_clean(); payment.save()
    for settlement in settlements:
        _sync_settlement_payment_status(settlement=settlement, actor_membership=actor_membership, request=request, reason=f"Payment {payment.payment_number} → {payment.get_status_display()}")
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action=f"rental.supplier_payment.{target}",
        object_type="rental_manpower.SupplierPayment", object_id=payment.pk, object_label=payment.payment_number,
        actor_membership=actor_membership, before={"status": before}, after={"status": payment.status, "reference": payment.transaction_reference},
        metadata={"reason": reason}, request=request,
    )
    return payment


@transaction.atomic
def retry_supplier_payment(*, actor_membership, payment_id, payment_date: date | None = None, request=None) -> SupplierPayment:
    _pay(actor_membership)
    company = actor_membership.company
    original = SupplierPayment.objects.select_for_update().for_company(company).select_related("supplier").get(pk=payment_id)
    if original.status not in {SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED}:
        raise ValidationError("Only Failed or Reversed supplier payments can be retried.")
    retry_date = payment_date or timezone.localdate()
    if retry_date < original.payment_date:
        raise ValidationError({"payment_date": "Retry payment date cannot be earlier than the original payment date."})
    allocations = list(
        SupplierPaymentAllocation.objects.select_for_update().for_company(company)
        .filter(payment=original).select_related("settlement")
    )
    if not allocations:
        raise ValidationError("The original supplier payment has no settlement allocation to retry.")
    for allocation in allocations:
        settlement = SupplierSettlement.objects.select_for_update().for_company(company).get(pk=allocation.settlement_id)
        paid, processing = _allocation_totals(settlement)
        available = _money(settlement.total_net - paid - processing)
        if allocation.amount > available:
            raise ValidationError(f"{settlement.settlement_number} no longer has enough outstanding balance for this retry.")
    retry = SupplierPayment(
        company=company, supplier=original.supplier,
        payment_number=allocate_number(company=company, key="rental.supplier_payment", prefix="SPAY-", padding=6),
        payment_date=retry_date, method=original.method, amount=original.amount,
        status=SupplierPaymentStatus.PROCESSING, transaction_reference="", note=original.note,
        supplier_code=original.supplier_code, supplier_name=original.supplier_name, retry_of=original,
    )
    retry.full_clean(); retry.save()
    for allocation in allocations:
        new_allocation = SupplierPaymentAllocation(company=company, payment=retry, settlement_id=allocation.settlement_id, amount=allocation.amount)
        new_allocation.full_clean(); new_allocation.save()
        settlement = SupplierSettlement.objects.select_for_update().for_company(company).get(pk=allocation.settlement_id)
        _sync_settlement_payment_status(settlement=settlement, actor_membership=actor_membership, request=request)
    record_audit_event(
        company=company, area=AuditArea.RENTAL, action="rental.supplier_payment.retried",
        object_type="rental_manpower.SupplierPayment", object_id=retry.pk, object_label=retry.payment_number,
        actor_membership=actor_membership,
        after={"status": retry.status, "amount": str(retry.amount)},
        metadata={"retry_of": str(original.pk), "retry_of_number": original.payment_number}, request=request,
    )
    return retry
