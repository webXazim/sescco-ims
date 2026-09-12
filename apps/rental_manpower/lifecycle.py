from __future__ import annotations

from typing import Mapping
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.lifecycle import LifecycleAction, LifecycleBlocker, LifecyclePolicy, register_lifecycle_policy
from apps.rental_manpower.models import ManpowerSupplier, RentalWorker, RentalWorkerStatus, SupplierStatus, WorkerAssignment


def _open_assignment_count(worker: RentalWorker) -> int:
    today = timezone.localdate()
    return WorkerAssignment.objects.for_company(worker.company).filter(
        worker=worker, cancelled_at__isnull=True
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today)).count()


class ManpowerSupplierLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.RENTAL
    object_type = "rental_manpower.ManpowerSupplier"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE, LifecycleAction.DEACTIVATE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance): return instance.code

    def dependency_evidence(self, instance, action: LifecycleAction) -> Mapping[str, int]:
        active_workers = instance.workers.filter(status=RentalWorkerStatus.ACTIVE, archived_at__isnull=True).count()
        if action in {LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE}:
            return {"active_workers": active_workers}
        if action is LifecycleAction.DELETE:
            return {
                "workers": instance.workers.count(),
                "adjustments": instance.rental_settlement_adjustments.count(),
                "settlements": instance.rental_supplier_settlements.count(),
                "payments": instance.payments.count(),
            }
        return {}

    def blockers(self, instance, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at: return (LifecycleBlocker(code="already_archived", field="supplier", message="This manpower supplier is already archived."),)
            if instance.status != SupplierStatus.INACTIVE: return (LifecycleBlocker(code="supplier_still_active", field="supplier", message="Make the supplier inactive before archiving it."),)
            if evidence.get("active_workers", 0): return (LifecycleBlocker(code="active_workers", field="supplier", label="Active workers", count=evidence["active_workers"], message="Deactivate or release active workers before archiving this supplier."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at: return (LifecycleBlocker(code="not_archived", field="supplier", message="This manpower supplier is not archived."),)
            return ()
        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at: return (LifecycleBlocker(code="archived", field="supplier", message="Restore this supplier before changing its active status."),)
            if instance.status == SupplierStatus.INACTIVE: return (LifecycleBlocker(code="already_inactive", field="supplier", message="This manpower supplier is already inactive."),)
            if evidence.get("active_workers", 0): return (LifecycleBlocker(code="active_workers", field="supplier", label="Active workers", count=evidence["active_workers"], message="Deactivate or release active workers before making this supplier inactive."),)
            return ()
        if action is LifecycleAction.DELETE:
            total=sum(evidence.values())
            if total: return (LifecycleBlocker(code="historical_records_exist", field="supplier", label="Historical references", count=total, message="This supplier has worker or financial history. Archive it instead of deleting it."),)
            return ()
        return ()


class RentalWorkerLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.RENTAL
    object_type = "rental_manpower.RentalWorker"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE, LifecycleAction.DEACTIVATE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance): return instance.worker_number

    def dependency_evidence(self, instance, action: LifecycleAction) -> Mapping[str, int]:
        open_assignments = _open_assignment_count(instance)
        if action in {LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE}: return {"open_assignments": open_assignments}
        if action is LifecycleAction.DELETE:
            return {
                "assignments": instance.rental_assignments.count(),
                "timesheet_entries": instance.timesheet_entries.count(),
                "overtime_entries": instance.timesheet_overtime_entries.count(),
                "adjustments": instance.rental_settlement_adjustments.count(),
                "settlement_lines": instance.settlement_lines.count(),
            }
        return {}

    def blockers(self, instance, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at: return (LifecycleBlocker(code="already_archived", field="worker", message="This rental worker is already archived."),)
            if instance.status != RentalWorkerStatus.INACTIVE: return (LifecycleBlocker(code="worker_still_active", field="worker", message="Mark the worker inactive before archiving the record."),)
            if evidence.get("open_assignments", 0): return (LifecycleBlocker(code="open_assignments", field="worker", label="Current or scheduled assignments", count=evidence["open_assignments"], message="Release or cancel current/scheduled assignments before archiving this worker."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at: return (LifecycleBlocker(code="not_archived", field="worker", message="This rental worker is not archived."),)
            return ()
        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at: return (LifecycleBlocker(code="archived", field="worker", message="Restore this worker before changing worker status."),)
            if instance.status == RentalWorkerStatus.INACTIVE: return (LifecycleBlocker(code="already_inactive", field="worker", message="This rental worker is already inactive."),)
            if evidence.get("open_assignments", 0): return (LifecycleBlocker(code="open_assignments", field="worker", label="Current or scheduled assignments", count=evidence["open_assignments"], message="Release or cancel current/scheduled assignments before making this worker inactive."),)
            return ()
        if action is LifecycleAction.DELETE:
            total=sum(evidence.values())
            if total: return (LifecycleBlocker(code="historical_records_exist", field="worker", label="Historical references", count=total, message="This worker has assignment, timesheet, adjustment, or settlement history. Archive the worker instead of deleting it."),)
            return ()
        return ()


register_lifecycle_policy(ManpowerSupplier, ManpowerSupplierLifecyclePolicy())
register_lifecycle_policy(RentalWorker, RentalWorkerLifecyclePolicy())
