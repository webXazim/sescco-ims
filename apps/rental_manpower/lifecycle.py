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
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE, LifecycleAction.DELETE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance): return instance.code

    def dependency_evidence(self, instance, action: LifecycleAction) -> Mapping[str, int]:
        active_workers = instance.workers.filter(status=RentalWorkerStatus.ACTIVE, archived_at__isnull=True, deleted_at__isnull=True).count()
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
            # Active workers inherit the supplier archive boundary; their own
            # permanent worker state and assignment history are not rewritten.
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at: return (LifecycleBlocker(code="not_archived", field="supplier", message="This manpower supplier is not archived."),)
            return ()
        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at: return (LifecycleBlocker(code="archived", field="supplier", message="Restore this supplier before changing its active status."),)
            if instance.status == SupplierStatus.TERMINATED: return (LifecycleBlocker(code="terminated", field="supplier", message="This manpower supplier is terminated. Start a new supplier relationship if business resumes."),)
            if instance.status == SupplierStatus.INACTIVE: return (LifecycleBlocker(code="already_inactive", field="supplier", message="This manpower supplier is already inactive."),)
            # Temporary supplier stop is inherited by the worker register.
            # Worker masters and assignment history stay untouched so reactivation can resume safely.
            return ()
        if action is LifecycleAction.DELETE:
            # The supplier is the lifecycle parent for its worker register. Delete
            # is a reversible 30-day boundary and does not require deactivating
            # every worker first.
            return ()
        return ()


class RentalWorkerLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.RENTAL
    object_type = "rental_manpower.RentalWorker"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE, LifecycleAction.DEACTIVATE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE, LifecycleAction.DELETE})
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
            # Archive suspends new operational use without rewriting assignment
            # history or forcing an employment/status transition first.
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at: return (LifecycleBlocker(code="not_archived", field="worker", message="This rental worker is not archived."),)
            return ()
        if action is LifecycleAction.DEACTIVATE:
            if instance.archived_at: return (LifecycleBlocker(code="archived", field="worker", message="Restore this worker before changing worker status."),)
            if instance.status == RentalWorkerStatus.TERMINATED: return (LifecycleBlocker(code="terminated", field="worker", message="This rental worker is terminated. Create a new onboarding record if the worker returns."),)
            if instance.status == RentalWorkerStatus.INACTIVE: return (LifecycleBlocker(code="already_inactive", field="worker", message="This rental worker is already inactive."),)
            # Temporary worker stop does not rewrite the open assignment.
            # Inactive status blocks new operational entries and can be safely reactivated later.
            return ()
        if action is LifecycleAction.DELETE:
            # Soft delete is independent of worker status and assignment history.
            # Existing history remains protected and the master is recoverable for
            # the configured retention window.
            return ()
        return ()


register_lifecycle_policy(ManpowerSupplier, ManpowerSupplierLifecyclePolicy())
register_lifecycle_policy(RentalWorker, RentalWorkerLifecyclePolicy())
