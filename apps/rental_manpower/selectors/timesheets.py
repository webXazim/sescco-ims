from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal
from django.db.models import Q

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.rental_manpower.models import RentalTimesheetPeriod, RentalTimesheetEntry, RentalTimesheetOvertime, RentalTimesheetStatus, WorkerAssignment
from apps.rental_manpower.services.timesheets import month_bounds
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id


def _display(entry):
    if entry.code: return entry.code
    return str(int(entry.regular_hours)) if entry.regular_hours == entry.regular_hours.to_integral() else format(entry.regular_hours.normalize(),'f')


def rental_timesheet_context(*, company, project_id, period_start: date, membership=None):
    start,end=month_bounds(period_start)
    project = rental_project_for_company(company=company, identifier=project_id) if project_id else None
    period=(RentalTimesheetPeriod.objects.for_company(company).select_related('project').filter(project=project,period_start=start).first() if project else None)
    assignments=[]
    if project:
        assignments=list(WorkerAssignment.objects.for_company(company).select_related('worker','worker__supplier','project').filter(project=project,cancelled_at__isnull=True,effective_from__lte=end).filter(Q(effective_to__isnull=True)|Q(effective_to__gte=start)).order_by('worker__worker_number','effective_from'))
    workers={str(a.worker_id):a.worker for a in assignments}
    entries=list(RentalTimesheetEntry.objects.for_company(company).filter(period=period).select_related('worker','assignment') if period else [])
    overtime=list(RentalTimesheetOvertime.objects.for_company(company).filter(period=period).select_related('worker','assignment') if period else [])
    records={}
    for e in entries: records.setdefault(str(e.worker_id),{})[str(e.work_date.day)]=_display(e)
    ot={str(o.worker_id):{'hours':str(o.hours),'rate':str(o.rate),'trade':o.trade,'rateType':o.rate_type} for o in overtime}
    can_edit=bool(membership and membership_can_edit(membership,Workspace.RENTAL) and (period is None or period.status==RentalTimesheetStatus.DRAFT))
    can_approve=bool(membership and membership_can_workspace(membership,Workspace.RENTAL) and membership_has_capability(membership,Capability.APPROVE))
    status=period.status if period else RentalTimesheetStatus.DRAFT
    next_action='submit' if status==RentalTimesheetStatus.DRAFT and can_edit else ('approve' if status==RentalTimesheetStatus.SUBMITTED and can_approve else ('lock' if status==RentalTimesheetStatus.APPROVED and can_approve else None))
    roster=[]
    for wid,w in sorted(workers.items(),key=lambda item:item[1].worker_number):
        segments=[]
        for a in assignments:
            if str(a.worker_id)!=wid: continue
            segments.append({'id':str(a.pk),'projectId':project_public_id(a.project),'start':a.effective_from.isoformat(),'end':a.effective_to.isoformat() if a.effective_to else None,'trade':a.trade,'rateType':a.rate_type,'rate':str(a.rate),'supplierId':str(a.worker.supplier_id),'supplierName':a.worker.supplier.name})
        roster.append({'id':wid,'workerId':w.worker_number,'name':w.full_name,'supplierId':str(w.supplier_id),'supplierName':w.supplier.name,'assignments':segments})
    regular_hours=sum((e.regular_hours for e in entries),Decimal('0')); ot_hours=sum((o.hours for o in overtime),Decimal('0'))
    return {'period':{'id':str(period.pk) if period else None,'exists':period is not None,'period':f'{start:%Y-%m}','label':f'{month_name[start.month]} {start.year}','start':start.isoformat(),'end':end.isoformat(),'projectId':project_public_id(project) if project else None,'status':RentalTimesheetStatus(status).label,'statusValue':status,'revision':period.revision if period else 0,'canEdit':can_edit,'canApprove':can_approve,'nextAction':next_action},'roster':roster,'records':records,'overtime':ot,'summary':{'workerCount':len(roster),'entryCount':len(entries),'regularHours':str(regular_hours),'overtimeHours':str(ot_hours)}}
