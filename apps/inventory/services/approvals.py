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
from apps.accounts.permissions import user_membership_for_company
from apps.projects.models import Project
from ..models import InventoryLocation, StockApprovalDecision, StockApprovalRequest, StockItem, Unit
from .stock import InventoryOperationError, _require_inventory_permission


def _projects_for_locations(*locations):
    return sorted({loc.project_id for loc in locations if loc and loc.project_id})


def _verify_managers(company, project_ids):
    projects = list(Project.objects.for_company(company).select_related("inventory_manager").filter(pk__in=project_ids))
    if len(projects) != len(project_ids):
        raise InventoryOperationError("A project involved in this request no longer exists.")
    for project in projects:
        if not project.inventory_manager_id:
            raise InventoryOperationError(f"Assign a project inventory approver to {project.code} before submitting stock requests.")
        membership = user_membership_for_company(project.inventory_manager, company)
        if not membership or not membership_has_permission(membership, AccessPermission.INVENTORY_STOCK_APPROVE) or not membership_allows_project(membership, project):
            raise InventoryOperationError(f"{project.code} requires an active assigned user with project inventory approval permission and project scope.")
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
        projects = _verify_managers(company, project_ids)
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
    member = user_membership_for_company(user, project.company)
    return bool(
        user.is_active and project.inventory_manager_id == user.pk and member
        and membership_has_permission(member, AccessPermission.INVENTORY_STOCK_APPROVE)
        and membership_allows_project(member, project)
    )


def _apply(req):
    """Replay immutable submission through the original stock services and their validations."""
    from .stock import add_stock
    from .transfers import TransferAllocation, transfer_stock

    # Existing approvals cannot outlive reassignment or revocation. Check every
    # affected project's *current* approver before committing stock.
    project_ids = list(req.decisions.values_list("project_id", flat=True))
    if not project_ids:
        raise InventoryOperationError("The approval request no longer contains any project decisions.")
    _verify_managers(req.company, project_ids)
    for row in req.decisions.select_related("project", "decided_by"):
        if row.status != StockApprovalDecision.Status.APPROVED or row.decided_by_id != row.project.inventory_manager_id or not can_decide(row.decided_by, row.project):
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
        raise InventoryOperationError("Only the currently assigned project inventory approver can decide for this project.")
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
