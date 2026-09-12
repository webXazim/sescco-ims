from __future__ import annotations

from apps.rental_manpower.project_adapter import rental_project_for_company

from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.permissions import membership_can_edit, membership_has_capability, membership_can_workspace
from apps.accounts.roles import Capability, Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.rental_manpower.models import (
    RentalAttendanceCode, RentalTimesheetEntry, RentalTimesheetOvertime,
    RentalTimesheetPeriod, RentalTimesheetStatus, RentalRateType, WorkerAssignment,
    RentalWorkerStatus, SupplierStatus,
)


def month_bounds(period_start: date):
    start = period_start.replace(day=1)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


def _edit(membership):
    if not membership_can_edit(membership, Workspace.RENTAL):
        raise PermissionDenied("Your role cannot edit rental timesheets.")


def _approve(membership):
    if not membership_can_workspace(membership, Workspace.RENTAL) or not membership_has_capability(membership, Capability.APPROVE):
        raise PermissionDenied("Your role cannot approve rental timesheets.")


def _decimal(value, field, *, maximum=None):
    try: v=Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError): raise ValidationError({field: "Enter a valid number."})
    if v < 0 or (maximum is not None and v > maximum): raise ValidationError({field: f"Enter a value between 0 and {maximum}."})
    return v


def _period(*, company, project_id, period_start, create=False, require_active=False):
    start,end=month_bounds(period_start)
    project=rental_project_for_company(company=company, identifier=project_id, require_active=require_active)
    qs=RentalTimesheetPeriod.objects.select_for_update().filter(company=company, project=project, period_start=start)
    obj=qs.first()
    if obj is None and create:
        obj=RentalTimesheetPeriod(company=company, project=project, period_start=start, period_end=end)
        obj.full_clean(); obj.save()
    return project,obj


def _assert_assignment_lifecycle(assignment, *, work_date=None):
    worker = assignment.worker
    supplier = worker.supplier
    if worker.deleted_at or supplier.deleted_at:
        raise ValidationError({"worker_id": "Restore the deleted worker/supplier lifecycle before editing timesheets."})
    if worker.archived_at or supplier.archived_at:
        raise ValidationError({"worker_id": "Restore the archived worker/supplier lifecycle before editing timesheets."})

    # Temporary stop and termination are effective-dated operational boundaries.
    # Historical draft corrections through the effective date remain possible; new
    # activity after that date is blocked. When no work date is available (for
    # example a monthly OT aggregate), stopped/terminated masters stay blocked.
    if worker.status == RentalWorkerStatus.INACTIVE:
        if work_date is None or not worker.inactive_on or work_date > worker.inactive_on:
            raise ValidationError({"worker_id": "The rental worker is temporarily stopped for new timesheet activity."})
    elif worker.status == RentalWorkerStatus.TERMINATED:
        if work_date is None or not worker.terminated_on or work_date > worker.terminated_on:
            raise ValidationError({"worker_id": "The rental worker relationship is terminated for new timesheet activity."})
    elif worker.status != RentalWorkerStatus.ACTIVE:
        raise ValidationError({"worker_id": "Only an active rental worker can receive new timesheet entries."})

    if supplier.status == SupplierStatus.INACTIVE:
        if work_date is None or not supplier.inactive_on or work_date > supplier.inactive_on:
            raise ValidationError({"worker_id": "The manpower supplier is temporarily stopped for new timesheet activity."})
    elif supplier.status == SupplierStatus.TERMINATED:
        if work_date is None or not supplier.terminated_on or work_date > supplier.terminated_on:
            raise ValidationError({"worker_id": "The manpower supplier relationship is terminated for new timesheet activity."})
    elif supplier.status != SupplierStatus.ACTIVE:
        raise ValidationError({"worker_id": "The manpower supplier is not active for new timesheet activity."})


def _assignment(*, company, worker_id, project_id, work_date):
    obj=(WorkerAssignment.objects.for_company(company).select_related('worker','worker__supplier','project')
         .filter(worker_id=worker_id, project_id=project_id, cancelled_at__isnull=True, effective_from__lte=work_date)
         .filter(Q(effective_to__isnull=True)|Q(effective_to__gte=work_date)).order_by('-effective_from','-created_at').first())
    if obj is None: raise ValidationError({"worker_id": "Worker has no assignment to this project on the selected date."})
    _assert_assignment_lifecycle(obj, work_date=work_date)
    return obj


def _entry_snapshot(a):
    return dict(supplier_code=a.worker.supplier.code, supplier_name=a.worker.supplier.name, project_code=a.project.code,
                project_name=a.project.name, trade=a.trade, rate_type=a.rate_type, rate=a.rate)

@transaction.atomic
def save_entries(*, actor_membership, project_id, period_start, entries, request=None):
    _edit(actor_membership); company=actor_membership.company
    project,period=_period(company=company, project_id=project_id, period_start=period_start, create=True, require_active=True)
    if period.status != RentalTimesheetStatus.DRAFT: raise ValidationError("Only Draft rental timesheets can be edited.")
    changed=0
    for row in entries:
        worker_id=row.get('worker_id'); work_date=row.get('work_date')
        if not worker_id or not isinstance(work_date,date): raise ValidationError("worker_id and work_date are required.")
        a=_assignment(company=company, worker_id=worker_id, project_id=project.pk, work_date=work_date)
        raw=str(row.get('value','')).strip().upper(); code=''; hours=Decimal('0')
        if raw == '':
            deleted,_=RentalTimesheetEntry.objects.filter(company=company,period=period,worker_id=worker_id,work_date=work_date).delete()
            changed += 1 if deleted else 0
            continue
        if raw in {v for v,_ in RentalAttendanceCode.choices}: code=raw
        else: hours=_decimal(raw,'value',maximum=24)
        defaults={"company":company,"assignment":a,"regular_hours":hours,"code":code,"note":str(row.get('note') or '').strip(),**_entry_snapshot(a)}
        obj,created=RentalTimesheetEntry.objects.update_or_create(period=period,worker_id=worker_id,work_date=work_date,defaults=defaults)
        obj.full_clean(); changed += 1
    if changed:
        period.revision += 1; period.save(update_fields=['revision','updated_at'])
        record_audit_event(company=company,area=AuditArea.RENTAL,action='rental.timesheet.entries_saved',object_type='rental_manpower.RentalTimesheetPeriod',object_id=period.pk,actor_membership=actor_membership,object_label=f'{project.code} {period.period_start:%Y-%m}',metadata={'changed':changed,'revision':period.revision},request=request)
    return period

@transaction.atomic
def save_overtime(*, actor_membership, project_id, period_start, worker_id, hours, rate=None, request=None):
    _edit(actor_membership); company=actor_membership.company
    project,period=_period(company=company, project_id=project_id, period_start=period_start, create=True, require_active=True)
    if period.status != RentalTimesheetStatus.DRAFT: raise ValidationError("Only Draft rental timesheets can be edited.")
    h=_decimal(hours,'hours',maximum=744)
    if h == 0:
        RentalTimesheetOvertime.objects.filter(company=company,period=period,worker_id=worker_id).delete()
    else:
        assignments=list(WorkerAssignment.objects.for_company(company).select_related('worker','worker__supplier','project').filter(worker_id=worker_id,project=project,cancelled_at__isnull=True,effective_from__lte=period.period_end).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=period.period_start)).order_by('effective_from'))
        for assignment in assignments:
            _assert_assignment_lifecycle(assignment, work_date=period.period_end)
        commercial={(a.rate_type,a.rate,a.trade) for a in assignments}
        if len(commercial)!=1: raise ValidationError({"hours":"Overtime cannot be entered as one monthly value when trade/rate changes inside the period. Split/correct the assignment or use daily overtime in a future adjustment workflow."})
        a=assignments[0]
        if rate in (None, '') and a.rate_type != RentalRateType.HOURLY:
            raise ValidationError({"rate": "An explicit hourly OT rate is required for Daily or Monthly rental assignments."})
        overtime_rate=_decimal(rate if rate not in (None,'') else a.rate,'rate')
        if overtime_rate <= 0:
            raise ValidationError({"rate": "OT rate must be greater than zero."})
        obj,_=RentalTimesheetOvertime.objects.update_or_create(period=period,worker_id=worker_id,defaults={"company":company,"assignment":a,"hours":h,"rate":overtime_rate,**{k:v for k,v in _entry_snapshot(a).items() if k!='rate'}})
        obj.full_clean()
    period.revision += 1; period.save(update_fields=['revision','updated_at'])
    record_audit_event(company=company,area=AuditArea.RENTAL,action='rental.timesheet.overtime_saved',object_type='rental_manpower.RentalTimesheetPeriod',object_id=period.pk,actor_membership=actor_membership,metadata={'worker_id':str(worker_id),'hours':str(h),'revision':period.revision},request=request)
    return period


def _missing(period):
    required=[]
    assignments=WorkerAssignment.objects.for_company(period.company).filter(project=period.project,cancelled_at__isnull=True,effective_from__lte=period.period_end).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=period.period_start))
    saved=set(RentalTimesheetEntry.objects.filter(period=period).values_list('worker_id','work_date'))
    for a in assignments:
        start=max(a.effective_from,period.period_start); end=min(a.effective_to or period.period_end,period.period_end)
        d=start
        from datetime import timedelta
        while d<=end:
            if (a.worker_id,d) not in saved: required.append((a.worker_id,d))
            d += timedelta(days=1)
    return required

@transaction.atomic
def transition_timesheet(*, actor_membership, project_id, period_start, action, reason='', request=None):
    company=actor_membership.company; project,period=_period(company=company,project_id=project_id,period_start=period_start,create=False)
    if period is None: raise ValidationError("Timesheet does not exist.")
    action=action.strip().lower(); now=timezone.now(); before=period.status
    if action=='submit':
        _edit(actor_membership)
        if period.status!=RentalTimesheetStatus.DRAFT: raise ValidationError("Only Draft timesheets can be submitted.")
        missing=_missing(period)
        if missing: raise ValidationError({"entries":f"Timesheet has {len(missing)} missing assigned worker-day values."})
        period.status=RentalTimesheetStatus.SUBMITTED; period.submitted_at=now; period.submitted_by=actor_membership.user
    elif action=='approve':
        _approve(actor_membership)
        if period.status!=RentalTimesheetStatus.SUBMITTED: raise ValidationError("Only Submitted timesheets can be approved.")
        period.status=RentalTimesheetStatus.APPROVED; period.approved_at=now; period.approved_by=actor_membership.user
    elif action=='lock':
        _approve(actor_membership)
        if period.status!=RentalTimesheetStatus.APPROVED: raise ValidationError("Only Approved timesheets can be locked.")
        period.status=RentalTimesheetStatus.LOCKED; period.locked_at=now; period.locked_by=actor_membership.user
    elif action=='return':
        _approve(actor_membership)
        if period.status not in {RentalTimesheetStatus.SUBMITTED,RentalTimesheetStatus.APPROVED}: raise ValidationError("Only Submitted or Approved timesheets can be returned.")
        if not reason.strip(): raise ValidationError({"reason":"A correction reason is required."})
        period.status=RentalTimesheetStatus.DRAFT; period.approved_at=None; period.approved_by=None; period.submitted_at=None; period.submitted_by=None; period.revision += 1
    else: raise ValidationError({"action":"Action must be submit, approve, lock, or return."})
    period.save()
    record_audit_event(company=company,area=AuditArea.RENTAL,action=f'rental.timesheet.{action}',object_type='rental_manpower.RentalTimesheetPeriod',object_id=period.pk,actor_membership=actor_membership,before={'status':before},after={'status':period.status,'revision':period.revision},metadata={'reason':reason.strip()},request=request)
    return period
