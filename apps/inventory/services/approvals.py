"""Project-level two-sided stock approvals. A pending request never mutates stock."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import user_membership_for_company
from apps.projects.models import Project
from ..models import InventoryLocation, StockApprovalDecision, StockApprovalRequest, StockItem, Unit
from .stock import InventoryOperationError, _require_inventory_permission


def _projects_for_locations(*locations):
    return sorted({loc.project_id for loc in locations if loc and loc.project_id})


def _valid_approver_membership(membership, project):
    """Only the explicit approval grant and current company/project scope confer authority.

    A designated Inventory approver or Project Pulse manager is informative, not
    an authorization override. Custom profiles are first-class approval profiles.
    """
    return bool(
        membership and membership_has_permission(membership, AccessPermission.INVENTORY_STOCK_APPROVE)
        and membership_allows_project(membership, project)
    )


def _eligible_project_approvers(project):
    """Return active users with approval permission for this specific project."""
    memberships = CompanyMembership.objects.select_related(
        "user", "company", "access_profile"
    ).filter(
        company_id=project.company_id, is_active=True, user__is_active=True,
        access_profile__is_active=True,
        access_profile__permission_grants__permission=AccessPermission.INVENTORY_STOCK_APPROVE.value,
    ).distinct()
    return {membership.user_id for membership in memberships if _valid_approver_membership(membership, project)}


def _require_projects(company, project_ids):
    """Validate request project identities, without requiring an approver at submission.

    Requests remain pending until an appropriately scoped permission holder decides.
    No project stock can post without each required approval.
    """
    projects = list(Project.objects.for_company(company).filter(pk__in=project_ids))
    if len(projects) != len(set(project_ids)):
        raise InventoryOperationError("A project involved in this request no longer exists.")
    return projects


def queue_request(*, company, requested_by, kind, idempotency_key, project_ids, payload, attachment=None):
    """Create pending work atomically; no balance, transfer or movement is written."""
    if kind not in StockApprovalRequest.Kind.values or not project_ids:
        raise InventoryOperationError("Only project stock requests can enter approval.")
    with transaction.atomic():
        # Serialize same-company submissions before the uniqueness check, including
        # rapid double clicks arriving in independent workers.
        type(company).objects.select_for_update().get(pk=company.pk)
        prior = StockApprovalRequest.objects.for_company(company).filter(kind=kind, idempotency_key=idempotency_key).first()
        if prior:
            return prior, True
        projects = _require_projects(company, project_ids)
        req = StockApprovalRequest.objects.create(
            company=company, requested_by=requested_by, kind=kind, idempotency_key=idempotency_key,
            payload=payload, attachment=attachment,
        )
        StockApprovalDecision.objects.bulk_create([
            StockApprovalDecision(request=req, project=p) for p in projects
        ])
        from apps.core.models import AuditArea
        from apps.core.services.audit import record_audit_event
        record_audit_event(
            company=company, area=AuditArea.INVENTORY,
            action="inventory.stock_approval.submitted",
            object_type="inventory.StockApprovalRequest", object_id=req.reference,
            object_label=str(req), actor=requested_by,
            actor_membership=user_membership_for_company(requested_by, company),
            after={"status": "pending", "kind": kind, "projects": project_ids},
        )
        return req, False


def can_decide(user, project):
    membership = user_membership_for_company(user, project.company)
    return bool(
        user.is_active and _valid_approver_membership(membership, project)
    )


def _apply(req):
    """Replay immutable submission through the original stock services and their validations."""
    from .stock import add_stock
    from .transfers import TransferAllocation, transfer_stock

    # Re-check each decision maker's CURRENT approval grant and project scope.
    # A manager assignment change alone must not override explicit profile grants.
    project_ids = list(req.decisions.values_list("project_id", flat=True))
    if not project_ids:
        raise InventoryOperationError("The approval request no longer contains any project decisions.")
    _require_projects(req.company, project_ids)
    for row in req.decisions.select_related("project", "decided_by"):
        if row.status != StockApprovalDecision.Status.APPROVED or not row.decided_by_id or not can_decide(row.decided_by, row.project):
            raise InventoryOperationError("The project inventory approver assignment or approval access changed. Reject and resubmit this request.")
    payload = req.payload
    if req.kind == StockApprovalRequest.Kind.RECEIPT:
        project = Project.objects.for_company(req.company).get(pk=payload["project_id"])
        unit = Unit.objects.for_company(req.company).get(pk=payload["unit_id"])
        result = add_stock(
            user=req.requested_by, idempotency_key=req.idempotency_key,
            project=project, quantity=Decimal(payload["quantity"]),
            movement_date=date.fromisoformat(payload["movement_date"]),
            condition=payload["condition"], material_name=payload["material_name"],
            supplier_name=payload["supplier_name"], supplier_phone=payload["supplier_phone"],
            unit=unit, description=payload["description"], supplier_location=payload["supplier_location"],
            minimum_quantity=Decimal(payload["minimum_quantity"]),
            unit_price=Decimal(payload["unit_price"]) if payload["unit_price"] is not None else None,
            invoice_reference=payload["invoice_reference"], notes=payload["notes"],
            attachment=req.attachment if req.attachment else None,
            confirm_similar=payload["confirm_similar"], approved_request=req,
        )
        if not result.movement:
            raise InventoryOperationError("Approved receipt did not create a movement.")
        req.applied_movement = result.movement
    else:
        source = InventoryLocation.objects.for_company(req.company).get(pk=payload["source_location_id"])
        destination = InventoryLocation.objects.for_company(req.company).get(pk=payload["destination_location_id"])
        item_ids = [line["stock_item_id"] for line in payload["allocations"]]
        items = {
            i.pk: i for i in StockItem.objects.for_company(req.company).filter(pk__in=item_ids)
        }
        if len(items) != len(set(item_ids)):
            raise InventoryOperationError("One of the requested stock records is unavailable.")
        result = transfer_stock(
            user=req.requested_by, idempotency_key=req.idempotency_key,
            source_location=source, destination_location=destination,
            transfer_date=date.fromisoformat(payload["transfer_date"]),
            allocations=[TransferAllocation(items[line["stock_item_id"]], line["outcome"], Decimal(line["quantity"])) for line in payload["allocations"]],
            document_reference=payload["document_reference"], notes=payload["notes"],
            attachment=req.attachment if req.attachment else None, approved_request=req,
        )
        if not result.transfer:
            raise InventoryOperationError("Approved transfer did not create a transfer.")
        req.applied_transfer = result.transfer
    req.status = StockApprovalRequest.Status.APPROVED
    req.decided_at = timezone.now()
    req.save(update_fields=("applied_movement", "applied_transfer", "status", "decided_at"))


@transaction.atomic
def decide_request(*, request, user, project_id, decision, reason=""):
    if decision not in ("approve", "reject"):
        raise InventoryOperationError("Invalid approval decision.")
    req = StockApprovalRequest.objects.for_company(request.company).select_for_update().get(pk=request.pk)
    if req.status != StockApprovalRequest.Status.PENDING:
        raise InventoryOperationError("This request is already finalized.")
    row = StockApprovalDecision.objects.select_for_update().select_related("project").filter(
        request=req, project_id=project_id,
    ).first()
    if row is None or not can_decide(user, row.project):
        raise InventoryOperationError("Only a user with Project Inventory Approve / Reject permission and access to this project can decide.")
    if req.requested_by_id == user.pk:
        raise InventoryOperationError("The requester cannot approve their own stock movement.")
    if row.status != StockApprovalDecision.Status.PENDING:
        raise InventoryOperationError("Your project has already decided this request.")
    if decision == "reject" and not reason.strip():
        raise InventoryOperationError("A rejection reason is required.")
    row.status = StockApprovalDecision.Status.APPROVED if decision == "approve" else StockApprovalDecision.Status.REJECTED
    row.reason = reason.strip()[:500]
    row.decided_at = timezone.now()
    row.decided_by = user
    row.save(update_fields=("status", "reason", "decided_at", "decided_by"))
    if decision == "reject":
        req.status = StockApprovalRequest.Status.REJECTED
        req.decided_at = timezone.now()
        req.save(update_fields=("status", "decided_at"))
    elif not req.decisions.exclude(status=StockApprovalDecision.Status.APPROVED).exists():
        # Last approval is the only place that stock is moved. Any failure rolls back
        # this decision and all stock changes so the pending request can be reviewed.
        try:
            _apply(req)
        except ObjectDoesNotExist as exc:
            raise InventoryOperationError("A referenced project, unit or stock item no longer exists. Reject and resubmit.") from exc
    from apps.core.models import AuditArea
    from apps.core.services.audit import record_audit_event
    record_audit_event(
        company=req.company, area=AuditArea.INVENTORY,
        action="inventory.stock_approval.approved" if decision == "approve" else "inventory.stock_approval.rejected",
        object_type="inventory.StockApprovalRequest", object_id=req.reference,
        object_label=str(req), actor=user, actor_membership=user_membership_for_company(user, req.company),
        after={"status": req.status, "project_id": project_id, "decision": decision, "reason": row.reason},
    )
    return req


@transaction.atomic
def cancel_pending_transfer(*, request, user, reason):
    """Cancel the requester's unposted transfer without changing inventory.

    Lock the same request row used by decide_request: only one of cancellation
    or final approval can win. Keep any previous per-project decisions intact.
    """
    req = StockApprovalRequest.objects.for_company(request.company).select_for_update().get(pk=request.pk)
    membership = user_membership_for_company(user, req.company)
    if not membership or not user.is_active or req.requested_by_id != user.pk:
        raise InventoryOperationError("Only the active original requester can cancel this transfer.")
    if req.kind != StockApprovalRequest.Kind.TRANSFER:
        raise InventoryOperationError("Only stock transfer requests can be cancelled here.")
    if req.status != StockApprovalRequest.Status.PENDING or req.applied_transfer_id:
        raise InventoryOperationError("Only pending, unposted transfers can be cancelled.")
    reason = (reason or "").strip()
    if not reason:
        raise InventoryOperationError("A cancellation reason is required.")
    req.status = StockApprovalRequest.Status.CANCELLED
    req.cancelled_by = user
    req.cancellation_reason = reason[:500]
    req.decided_at = timezone.now()
    req.save(update_fields=("status", "cancelled_by", "cancellation_reason", "decided_at"))

    from apps.core.models import AuditArea
    from apps.core.services.audit import record_audit_event
    record_audit_event(
        company=req.company, area=AuditArea.INVENTORY,
        action="inventory.stock_approval.cancelled",
        object_type="inventory.StockApprovalRequest", object_id=req.reference,
        object_label=str(req), actor=user, actor_membership=membership,
        after={"status": req.status, "kind": req.kind, "reason": req.cancellation_reason},
    )
    return req


def pending_visible_request_count(*, company, user, membership):
    """Count distinct pending requests visible to this user, including their own.

    This mirrors the review inbox: a submitter can track their requests and an
    approver can see requests for authorized projects. Other tenants are never
    counted. Two-project transfers are counted once.
    """
    if (
        not company or not user or not user.is_authenticated or not user.is_active
        or not membership or not membership.is_active or membership.company_id != company.pk
    ):
        return 0
    from django.db.models import Q
    from apps.accounts.access_policy import restrict_projects
    eligible_ids = []
    if membership_has_permission(membership, AccessPermission.INVENTORY_STOCK_APPROVE):
        pending_project_ids = StockApprovalDecision.objects.filter(
            request__company=company,
            request__status=StockApprovalRequest.Status.PENDING,
            status=StockApprovalDecision.Status.PENDING,
        ).values_list("project_id", flat=True).distinct()
        candidates = restrict_projects(
            Project.objects.for_company(company).filter(
                deleted_at__isnull=True, pk__in=pending_project_ids,
            ), membership
        )
        eligible_ids = [p.pk for p in candidates if _valid_approver_membership(membership, p)]
    return (
        StockApprovalRequest.objects.for_company(company)
        .filter(status=StockApprovalRequest.Status.PENDING)
        .filter(Q(requested_by_id=user.pk) | Q(decisions__project_id__in=eligible_ids))
        .distinct().count()
    )
