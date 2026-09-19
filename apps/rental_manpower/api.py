from __future__ import annotations

from apps.projects.contracts import ProjectStatus
from apps.rental_manpower.project_adapter import rental_project_for_company, rental_projects_for_company, project_public_id
from apps.projects.services import archive_project, restore_project_archive, trash_unused_project, restore_project_trash
from apps.projects.models import Project

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Case, Count, DecimalField, Exists, F, OuterRef, Q, Sum, Value, When
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models.functions import Coalesce

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission, project_scope_ids, restrict_projects
from apps.accounts.roles import Workspace
from apps.core.query_controls import ListControls, apply_ordering, parse_list_controls, serialize_list
from apps.core.payroll_attendance_contract import normalize_attendance_workflow_action
from apps.rental_manpower.api_utils import handle_api_error, json_body, parse_date, parse_optional_date
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    RentalAdjustment,
    AssignmentChangeType,
    WorkerAssignment,
    RentalSettlementStatus,
    SupplierPaymentStatus,
    SupplierSettlement,
)
from apps.rental_manpower.selectors import (
    assignments_for_company,
    serialized_assignment_history,
    serialized_assignment_activity,
    projects_for_company,
    serialize_project,
    serialize_supplier,
    serialize_worker,
    suppliers_for_company,
    workers_for_company,
    worker_directory_summary,
    rental_adjustment_page_context,
    rental_settlement_context,
    rental_financial_metrics_for_period,
    serialize_rental_adjustment,
    with_supplier_invoice_authority,
)
from apps.rental_manpower.services import (
    assign_worker,
    cancel_scheduled_assignment,
    change_worker_rate,
    change_worker_trade,
    release_worker,
    transfer_worker,
    create_project,
    create_supplier,
    create_worker,
    import_workers,
    update_project,
    update_supplier,
    update_worker,
    archive_supplier, restore_supplier_archive, restore_supplier_trash, delete_unused_supplier, change_supplier_lifecycle, change_worker_lifecycle, restore_worker_trash, delete_unused_worker,
    calculate_project_settlements,
    create_rental_adjustment,
    record_supplier_payment,
    retry_supplier_payment,
    transition_project_settlements,
    transition_rental_adjustment,
    transition_supplier_payment,
    update_rental_adjustment,
)



def _period_start(value: object) -> date:
    raw = str(value or "").strip()
    if len(raw) == 7:
        raw += "-01"
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    if parsed.day != 1:
        raise ValidationError({"period": "Period must identify a calendar month."})
    return parsed


def _request_period(request: HttpRequest, body: dict[str, object] | None = None) -> date:
    raw: object = request.GET.get("period", "")
    if not raw and body is not None:
        raw = body.get("period", "")
    if not raw:
        raise ValidationError({"period": "Period is required in YYYY-MM format."})
    return _period_start(raw)


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite number."}) from exc

def _status_query(value: str, allowed: set[str], field: str = "status") -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized or normalized == "all":
        return ""
    if normalized not in allowed:
        raise ValidationError({field: "Unknown status filter."})
    return normalized

def _archived_query(value: str) -> bool | None:
    normalized=(value or "").strip().lower()
    if normalized in {"", "current", "false", "0", "no"}: return False
    if normalized in {"archived", "true", "1", "yes"}: return True
    if normalized == "all": return None
    raise ValidationError({"archived":"Archived filter must be current, archived, or all."})


def _require_permission(request: HttpRequest, permission: AccessPermission, message: str | None = None) -> None:
    if not membership_has_permission(request.company_membership, permission):
        raise PermissionDenied(message or "Your access profile does not allow this Rental Manpower action.")


def _require_any_permission(request: HttpRequest, *permissions: AccessPermission) -> None:
    if not any(membership_has_permission(request.company_membership, permission) for permission in permissions):
        raise PermissionDenied("Your access profile does not allow this Rental Manpower action.")


def _scoped_project(request: HttpRequest, identifier, *, require_active: bool = False):
    project = rental_project_for_company(company=request.company, identifier=identifier, require_active=require_active)
    if not membership_allows_project(request.company_membership, project):
        raise PermissionDenied("This Rental project is outside your assigned access scope.")
    return project


def _commercial_visible(request: HttpRequest) -> bool:
    return any(
        membership_has_permission(request.company_membership, permission)
        for permission in (AccessPermission.RENTAL_SETTLEMENTS_VIEW, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
    )


def _bounded_lookup_page(request: HttpRequest, rows, *, serializer, min_query: int = 2, allow_empty: bool = False) -> JsonResponse:
    query = str(request.GET.get("q", "") or "").strip()
    exact_id = str(request.GET.get("id", "") or "").strip()
    try:
        page = max(1, int(request.GET.get("page", 1)))
        page_size = min(25, max(1, int(request.GET.get("page_size", 10))))
    except (TypeError, ValueError):
        page, page_size = 1, 10
    if exact_id:
        rows = rows.filter(pk=exact_id)
        page = 1
    elif not allow_empty and len(query) < min_query:
        return JsonResponse({"ok": True, "results": [], "meta": {"page": 1, "pageSize": page_size, "hasPrevious": False, "hasNext": False, "requiresSearch": True}})
    start = (page - 1) * page_size
    window = list(rows[start:start + page_size + 1])
    has_next = len(window) > page_size
    return JsonResponse({
        "ok": True,
        "results": [serializer(item) for item in window[:page_size]],
        "meta": {"page": page, "pageSize": page_size, "hasPrevious": page > 1, "hasNext": has_next, "requiresSearch": not allow_empty},
    })


@require_http_methods(["GET"])
@api_workspace_required(Workspace.RENTAL)
def supplier_lookup_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_any_permission(request, AccessPermission.RENTAL_SUPPLIERS_VIEW, AccessPermission.RENTAL_WORKERS_MANAGE)
        query = str(request.GET.get("q", "") or "").strip()
        rows = ManpowerSupplier.objects.for_company(request.company).filter(
            status=SupplierStatus.ACTIVE, archived_at__isnull=True, deleted_at__isnull=True
        )
        scoped_project_ids = project_scope_ids(request.company_membership)
        if scoped_project_ids is not None:
            if not scoped_project_ids:
                rows = rows.none()
            else:
                rows = rows.filter(workers__rental_assignments__project_id__in=scoped_project_ids).distinct()
        if query:
            rows = rows.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(contact_person__icontains=query) | Q(phone__icontains=query))
        rows = rows.order_by("code", "name")
        return _bounded_lookup_page(
            request, rows,
            serializer=lambda item: {"id": str(item.pk), "code": item.code, "name": item.name, "meta": item.contact_person or item.phone or "Active supplier"},
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET"])
@api_workspace_required(Workspace.RENTAL)
def supplier_payment_settlement_lookup_api(request: HttpRequest) -> JsonResponse:
    """Return only settlements that can accept a new supplier payment allocation."""
    try:
        _require_permission(request, AccessPermission.RENTAL_PAYMENTS_PREPARE)
        query = str(request.GET.get("q", "") or "").strip()
        period_raw = str(request.GET.get("period", "") or "").strip()
        statuses = [RentalSettlementStatus.APPROVED, RentalSettlementStatus.PAYMENT_PROCESSING, RentalSettlementStatus.PARTIALLY_PAID]
        rows = restrict_projects(
            SupplierSettlement.objects.for_company(request.company).filter(status__in=statuses),
            request.company_membership,
            field="project_id",
        )
        if period_raw:
            rows = rows.filter(period_start=_period_start(period_raw))
        if query:
            rows = rows.filter(
                Q(settlement_number__icontains=query) | Q(supplier_code__icontains=query) | Q(supplier_name__icontains=query)
                | Q(project_code__icontains=query) | Q(project_name__icontains=query)
            )
        money_field = DecimalField(max_digits=18, decimal_places=2)
        rows = with_supplier_invoice_authority(rows, company=request.company)
        rows = rows.annotate(
            _paid=Coalesce(Sum("payment_allocations__amount", filter=Q(payment_allocations__payment__status=SupplierPaymentStatus.PAID)), Value(Decimal("0.00")), output_field=money_field),
            _processing=Coalesce(Sum("payment_allocations__amount", filter=Q(payment_allocations__payment__status=SupplierPaymentStatus.PROCESSING)), Value(Decimal("0.00")), output_field=money_field),
            _allocated=Coalesce(
                Sum(
                    "payment_allocations__amount",
                    filter=Q(payment_allocations__payment__status__in=[SupplierPaymentStatus.PAID, SupplierPaymentStatus.PROCESSING]),
                ),
                Value(Decimal("0.00")),
                output_field=money_field,
            ),
        ).annotate(
            _payable=Case(
                When(_supplier_invoice_total__gt=Decimal("0.00"), then=F("_supplier_invoice_total")),
                default=F("total_net"), output_field=money_field,
            )
        ).filter(
            Q(_supplier_invoice_number__isnull=False) | Q(_allocated__gt=Decimal("0.00")),
            _payable__gt=F("_allocated"),
        ).order_by("settlement_number")
        # Availability is revalidated transactionally on save; new payables require a received supplier invoice.
        return _bounded_lookup_page(
            request, rows, allow_empty=True, min_query=0,
            serializer=lambda item: {
                "id": str(item.pk), "code": item.settlement_number, "name": item.supplier_name,
                "meta": item.project_name, "supplier": item.supplier_name, "project": item.project_name,
                "paid": str(item._paid or Decimal("0.00")), "processing": str(item._processing or Decimal("0.00")),
                "available": str(item._payable - (item._paid or Decimal("0.00")) - (item._processing or Decimal("0.00"))),
                "amount": str(item._payable), "status": item.get_status_display(),
                "invoiceReceived": bool(item._supplier_invoice_number), "invoiceNumber": item._supplier_invoice_number or "",
            },
        )
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def suppliers_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_SUPPLIERS_VIEW if request.method == "GET" else AccessPermission.RENTAL_SUPPLIERS_MANAGE)
        if request.method == "GET":
            status = _status_query(request.GET.get("status", ""), {item.value for item in SupplierStatus})
            allowed_sorts = {
                "code": "code",
                "name": "name",
                "contact": "contact_person",
                "status": "status",
                "workers": "active_worker_count",
                "assigned": "assigned_worker_count",
                "projects": "active_project_count",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="code")
            project_id = request.GET.get("project_id") or None
            project_pk = None
            if project_id:
                project_pk = _scoped_project(request, project_id).pk
            payment_terms_raw = request.GET.get("payment_terms")
            payment_terms = "" if payment_terms_raw is None else str(payment_terms_raw).strip()
            payment_terms_blank = payment_terms == "__blank__"
            if payment_terms_blank:
                payment_terms = ""
            workforce = str(request.GET.get("workforce", "")).strip().lower()
            if workforce not in {"", "assigned", "available", "none"}:
                raise ValidationError({"workforce": "Workforce filter must be assigned, available, none, or blank."})
            rows = suppliers_for_company(
                company=request.company, query=request.GET.get("q", ""), status=status,
                archived=_archived_query(request.GET.get("archived", "")), project_id=project_pk,
                payment_terms=payment_terms, workforce=workforce,
            )
            scoped_project_ids = project_scope_ids(request.company_membership)
            if scoped_project_ids is not None:
                if not scoped_project_ids:
                    rows = rows.none()
                else:
                    today = timezone.localdate()
                    current_assignment = (
                        Q(workers__rental_assignments__cancelled_at__isnull=True)
                        & Q(workers__rental_assignments__effective_from__lte=today)
                        & (Q(workers__rental_assignments__effective_to__isnull=True) | Q(workers__rental_assignments__effective_to__gte=today))
                        & Q(workers__rental_assignments__project_id__in=scoped_project_ids)
                    )
                    rows = rows.filter(workers__rental_assignments__project_id__in=scoped_project_ids).annotate(
                        total_worker_count=Count("workers", filter=Q(workers__rental_assignments__project_id__in=scoped_project_ids), distinct=True),
                        active_worker_count=Count("workers", filter=Q(workers__status=RentalWorkerStatus.ACTIVE, workers__rental_assignments__project_id__in=scoped_project_ids), distinct=True),
                        assigned_worker_count=Count("workers", filter=Q(workers__status=RentalWorkerStatus.ACTIVE) & current_assignment, distinct=True),
                        active_project_count=Count("workers__rental_assignments__project", filter=Q(workers__status=RentalWorkerStatus.ACTIVE) & current_assignment, distinct=True),
                    ).distinct()
            if payment_terms_blank:
                rows = rows.filter(payment_terms="")
            period_raw = str(request.GET.get("period", "")).strip()
            metrics = (
                rental_financial_metrics_for_period(company=request.company, period_start=_period_start(period_raw))
                if period_raw and scoped_project_ids is None
                else {"suppliers": {}}
            )
            outstanding_filter = str(request.GET.get("outstanding", "")).strip().lower()
            if outstanding_filter not in {"", "open", "cleared"}:
                raise ValidationError({"outstanding": "Outstanding filter must be open, cleared, or blank."})
            if outstanding_filter:
                supplier_metrics = metrics.get("suppliers", {})
                matching_ids = [
                    supplier_id for supplier_id, bucket in supplier_metrics.items()
                    if (Decimal(str(bucket.get("outstanding") or 0)) > Decimal("0.005")) == (outstanding_filter == "open")
                ]
                if outstanding_filter == "cleared":
                    # Suppliers with no settlement snapshot are also cleared / none.
                    open_ids = [
                        supplier_id for supplier_id, bucket in supplier_metrics.items()
                        if Decimal(str(bucket.get("outstanding") or 0)) > Decimal("0.005")
                    ]
                    rows = rows.exclude(pk__in=open_ids)
                else:
                    rows = rows.filter(pk__in=matching_ids)
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            supplier_metrics = metrics.get("suppliers", {})
            results, meta = serialize_list(
                rows, controls=controls,
                serializer=lambda item: serialize_supplier(item, supplier_metrics.get(str(item.pk))),
            )
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = json_body(request)
        supplier = create_supplier(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            status=body.get("status", "Active"),
            contact_person=str(body.get("contact", "")),
            phone=str(body.get("phone", "")),
            email=str(body.get("email", "")),
            cr_number=str(body.get("cr", "")),
            vat_number=str(body.get("vat", "")),
            payment_terms=str(body.get("payment_terms", "")),
            address=str(body.get("address", "")),
            notes=str(body.get("notes", "")),
            request=request,
        )
        supplier = suppliers_for_company(company=request.company).get(pk=supplier.pk)
        return JsonResponse({"ok": True, "supplier": serialize_supplier(supplier)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.RENTAL)
def supplier_detail_api(request: HttpRequest, supplier_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_SUPPLIERS_MANAGE)
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id=delete_unused_supplier(actor_membership=request.company_membership, supplier_id=supplier_id, confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request)
            return JsonResponse({"ok":True,"deletedSupplierId":deleted_id})
        current = ManpowerSupplier.objects.for_company(request.company).get(pk=supplier_id)
        supplier = update_supplier(
            actor_membership=request.company_membership,
            supplier_id=supplier_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            status=body.get("status", current.get_status_display()),
            contact_person=str(body.get("contact", current.contact_person)),
            phone=str(body.get("phone", current.phone)),
            email=str(body.get("email", current.email)),
            cr_number=str(body.get("cr", current.cr_number)),
            vat_number=str(body.get("vat", current.vat_number)),
            payment_terms=str(body.get("payment_terms", current.payment_terms)),
            address=str(body.get("address", current.address)),
            notes=str(body.get("notes", current.notes)),
            request=request,
        )
        supplier = suppliers_for_company(company=request.company).get(pk=supplier.pk)
        return JsonResponse({"ok": True, "supplier": serialize_supplier(supplier)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def supplier_lifecycle_api(request: HttpRequest, supplier_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_SUPPLIERS_MANAGE)
        body=json_body(request); action=str(body.get("action","")).strip().lower().replace("-","_")
        effective=parse_optional_date(body.get("effective_date"), "effective_date")
        if action == "archive": supplier=archive_supplier(actor_membership=request.company_membership, supplier_id=supplier_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore","restore_archive"}: supplier=restore_supplier_archive(actor_membership=request.company_membership, supplier_id=supplier_id, reason=str(body.get("reason", "")), request=request)
        elif action == "restore_trash": supplier=restore_supplier_trash(actor_membership=request.company_membership, supplier_id=supplier_id, request=request)
        elif action in {"deactivate","inactive","activate","reactivate","active","terminate","terminated","stop_activity"}: supplier=change_supplier_lifecycle(actor_membership=request.company_membership, supplier_id=supplier_id, action=action, effective_date=effective, reason=str(body.get("reason", "")), request=request)
        else: raise ValidationError({"action":"Supplier lifecycle action must be deactivate, activate, terminate, archive, restore archive, or restore trash."})
        supplier=suppliers_for_company(company=request.company, archived=None).get(pk=supplier.pk)
        return JsonResponse({"ok":True,"supplier":serialize_supplier(supplier)})
    except Exception as exc: return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def projects_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_any_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_VIEW, AccessPermission.RENTAL_TIMESHEETS_VIEW) if request.method == "GET" else _require_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
        if request.method == "GET":
            status = _status_query(request.GET.get("status", ""), {item.value for item in ProjectStatus})
            allowed_sorts = {
                "code": "code",
                "name": "name",
                "client": "client_name",
                "location": "location",
                "manager": "manager_name",
                "start": "start_date",
                "status": "status",
                "workers": "assigned_worker_count",
                "suppliers": "assigned_supplier_count",
            }
            controls = parse_list_controls(
                request, allowed_sorts=allowed_sorts, default_sort="start", default_direction="desc"
            )
            client_raw = request.GET.get("client")
            manager_raw = request.GET.get("manager")
            client = None if client_raw is None else ("" if client_raw == "__blank__" else str(client_raw))
            manager = None if manager_raw is None else ("" if manager_raw == "__blank__" else str(manager_raw))
            supplier_id = request.GET.get("supplier_id") or None
            rows = projects_for_company(
                company=request.company, query=request.GET.get("q", ""), status=status,
                client=client, manager=manager, supplier_id=supplier_id, membership=request.company_membership,
            )
            period_raw = str(request.GET.get("period", "")).strip()
            metrics = (
                rental_financial_metrics_for_period(company=request.company, period_start=_period_start(period_raw))
                if period_raw and membership_has_permission(request.company_membership, AccessPermission.RENTAL_SETTLEMENTS_VIEW)
                else {"projects": {}}
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            project_metrics = metrics.get("projects", {})
            results, meta = serialize_list(
                rows, controls=controls,
                serializer=lambda item: serialize_project(item, project_metrics.get(str(item.reference))),
            )
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        if request.company_membership.project_scope_mode != "all":
            raise PermissionDenied("Project-scoped users cannot create Rental projects outside their assigned scope.")
        body = json_body(request)
        project = create_project(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            client_name=str(body.get("client", "")),
            location=str(body.get("location", "")),
            start_date=parse_date(body.get("start_date"), "start_date"),
            end_date=parse_optional_date(body.get("end_date"), "end_date"),
            manager_name=str(body.get("manager", "")),
            status=str(body.get("status", "Active")),
            notes=str(body.get("notes", "")),
            request=request,
        )
        return JsonResponse({"ok": True, "project": serialize_project(project)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.RENTAL)
def project_detail_api(request: HttpRequest, project_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
        _scoped_project(request, project_id)
        body = json_body(request)
        if request.method == "DELETE":
            project = trash_unused_project(
                actor_membership=request.company_membership, project_id=project_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedProjectId": str(project.reference)})
        current = rental_project_for_company(company=request.company, identifier=project_id)
        project = update_project(
            actor_membership=request.company_membership,
            project_id=project_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            client_name=str(body.get("client", current.client_name)),
            location=str(body.get("location", current.location)),
            start_date=parse_optional_date(body.get("start_date", current.start_date.isoformat() if current.start_date else None), "start_date"),
            end_date=parse_optional_date(body.get("end_date", current.end_date.isoformat() if current.end_date else None), "end_date"),
            manager_name=str(body.get("manager", current.manager_name)),
            status=str(body.get("status", current.get_status_display())),
            notes=str(body.get("notes", current.notes)),
            request=request,
        )
        return JsonResponse({"ok": True, "project": serialize_project(project)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def project_lifecycle_api(request: HttpRequest, project_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
        _scoped_project(request, project_id)
        body = json_body(request)
        action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            project = archive_project(actor_membership=request.company_membership, project_id=project_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            project = restore_project_archive(actor_membership=request.company_membership, project_id=project_id, reason=str(body.get("reason", "")), request=request)
        elif action == "restore_trash":
            project = restore_project_trash(actor_membership=request.company_membership, project_id=project_id, request=request)
        else:
            raise ValidationError({"action": "Project lifecycle action must be archive, restore archive, or restore trash."})
        return JsonResponse({"ok": True, "project": serialize_project(project)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def workers_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_WORKERS_VIEW if request.method == "GET" else AccessPermission.RENTAL_WORKERS_MANAGE)
        if request.method == "GET":
            view_status = str(request.GET.get("view_status", "")).strip().lower().replace(" ", "_")
            archived_raw = request.GET.get("archived", "")
            if view_status not in {"", "all", "assigned", "scheduled", "available", "inactive", "terminated", "archived"}:
                raise ValidationError({"view_status": "Unknown rental worker status filter."})
            if view_status == "archived":
                archived_raw = "archived"
            status = _status_query(request.GET.get("status", ""), {item.value for item in RentalWorkerStatus})
            supplier_id = request.GET.get("supplier_id") or None
            allowed_sorts = {
                "worker": "worker_number",
                "name": "full_name",
                "supplier": "supplier__name",
                "status": "status",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="worker")
            project_raw = request.GET.get("project_id") or None
            project_pk = None
            if project_raw == "unassigned":
                project_pk = "unassigned"
            elif project_raw:
                project_pk = _scoped_project(request, project_raw).pk
            rate_type = str(request.GET.get("rate_type", "")).strip().lower()
            if rate_type and rate_type not in {"hourly", "daily", "monthly"}:
                raise ValidationError({"rate_type": "Rate type must be hourly, daily, monthly, or blank."})
            rows = workers_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                status=status,
                supplier_id=supplier_id,
                archived=_archived_query(archived_raw),
                operational_status=view_status,
                project_id=project_pk,
                trade=str(request.GET.get("trade", "")).strip(),
                rate_type=rate_type,
                membership=request.company_membership,
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=lambda item: serialize_worker(item, include_commercial=_commercial_visible(request)))
            meta["summary"] = worker_directory_summary(company=request.company, membership=request.company_membership)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = json_body(request)
        worker = create_worker(
            actor_membership=request.company_membership,
            supplier_id=body.get("supplier_id"),
            worker_number=str(body.get("worker_number", "")),
            full_name=str(body.get("full_name", "")),
            national_id=str(body.get("national_id", "")),
            phone=str(body.get("phone", "")),
            status=body.get("status", "Active"),
            notes=str(body.get("notes", "")),
            request=request,
        )
        worker = workers_for_company(company=request.company).get(pk=worker.pk)
        return JsonResponse({"ok": True, "worker": serialize_worker(worker)}, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_workspace_required(Workspace.RENTAL)
def worker_detail_api(request: HttpRequest, worker_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_WORKERS_VIEW if request.method == "GET" else AccessPermission.RENTAL_WORKERS_MANAGE)
        if request.method == "GET":
            worker = workers_for_company(company=request.company, archived=None, membership=request.company_membership).get(pk=worker_id)
            assignments = restrict_projects(assignments_for_company(company=request.company, worker_id=worker_id), request.company_membership, field="project_id")
            assignments = list(assignments)
            return JsonResponse({
                "ok": True,
                "worker": serialize_worker(worker, include_commercial=_commercial_visible(request)),
                "assignments": serialized_assignment_history(company=request.company, assignments=assignments, include_commercial=_commercial_visible(request)),
            })
        body = json_body(request)
        if request.method == "DELETE":
            deleted_id=delete_unused_worker(actor_membership=request.company_membership, worker_id=worker_id, confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request)
            return JsonResponse({"ok":True,"deletedWorkerId":deleted_id})
        current = RentalWorker.objects.for_company(request.company).select_related("supplier").get(pk=worker_id)
        worker = update_worker(
            actor_membership=request.company_membership,
            worker_id=worker_id,
            worker_number=str(body.get("worker_number", current.worker_number)),
            full_name=str(body.get("full_name", current.full_name)),
            national_id=str(body.get("national_id", current.national_id)),
            phone=str(body.get("phone", current.phone)),
            supplier_id=body.get("supplier_id", current.supplier_id),
            status=body.get("status", current.get_status_display()),
            notes=str(body.get("notes", current.notes)),
            request=request,
        )
        worker = workers_for_company(company=request.company).get(pk=worker.pk)
        return JsonResponse({"ok": True, "worker": serialize_worker(worker)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def worker_lifecycle_api(request: HttpRequest, worker_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_WORKERS_MANAGE)
        body=json_body(request); action=str(body.get("action", "")).strip().lower().replace("-", "_")
        effective=parse_optional_date(body.get("effective_date"), "effective_date")
        if action == "restore_trash":
            worker=restore_worker_trash(actor_membership=request.company_membership, worker_id=worker_id, request=request)
        else:
            worker=change_worker_lifecycle(actor_membership=request.company_membership, worker_id=worker_id, action=action, effective_date=effective, reason=str(body.get("reason", "")), request=request)
        # Independent child recovery is valid while the supplier parent remains
        # in Delete.  Include inherited lifecycle rows so the response reflects
        # the worker as restored-own / inherited-deleted instead of failing after
        # the restore has already committed.
        worker=workers_for_company(company=request.company, archived=None, deleted=None).get(pk=worker.pk)
        return JsonResponse({"ok":True,"worker":serialize_worker(worker)})
    except Exception as exc: return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def workers_import_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_WORKERS_MANAGE)
        body = json_body(request)
        rows = body.get("rows")
        if not isinstance(rows, list):
            raise ValidationError({"rows": "rows must be an array."})
        dry_run = bool(body.get("dry_run", False))
        created = import_workers(
            actor_membership=request.company_membership,
            rows=rows,
            dry_run=dry_run,
            request=request,
        )
        results = [] if dry_run else [serialize_worker(item) for item in workers_for_company(company=request.company).filter(pk__in=[row.pk for row in created])]
        return JsonResponse(
            {
                "ok": True,
                "dryRun": dry_run,
                "validated": len(rows),
                "created": len(created),
                "workers": results,
            },
            status=200 if dry_run else 201,
        )
    except Exception as exc:
        return handle_api_error(exc)



def _assignment_worker_payload(*, company, worker_id, membership=None):
    worker = workers_for_company(company=company, membership=membership).get(pk=worker_id)
    assignments_qs = assignments_for_company(company=company, worker_id=worker_id)
    if membership is not None:
        assignments_qs = restrict_projects(assignments_qs, membership, field="project_id")
    assignments = list(assignments_qs)
    include_commercial = bool(membership is None or membership_has_permission(membership, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE))
    return {
        "worker": serialize_worker(worker, include_commercial=include_commercial),
        "assignments": serialized_assignment_history(company=company, assignments=assignments, include_commercial=include_commercial),
    }


def _bounded_list_controls(request: HttpRequest, *, allowed_sorts: dict[str, str], default_sort: str, default_direction: str = "asc") -> ListControls:
    controls = parse_list_controls(
        request,
        allowed_sorts=allowed_sorts,
        default_sort=default_sort,
        default_direction=default_direction,
        max_page_size=100,
    )
    if controls.page is None or controls.page_size is None:
        return ListControls(sort=controls.sort, direction=controls.direction, page=1, page_size=50)
    return controls


def _assignment_summary_payload(*, company, membership=None) -> dict[str, int]:
    assignments = WorkerAssignment.objects.for_company(company)
    if membership is not None:
        assignments = restrict_projects(assignments, membership, field="project_id")
    return {
        "assigned": workers_for_company(company=company, operational_status="assigned", membership=membership).count(),
        "available": workers_for_company(company=company, operational_status="available", membership=membership).count() if membership is None or membership.project_scope_mode == "all" else 0,
        "transfers": assignments.filter(change_type=AssignmentChangeType.TRANSFER).count(),
        "changes": assignments.filter(change_type__in=[AssignmentChangeType.TRADE_CHANGE, AssignmentChangeType.RATE_CHANGE]).count(),
        "releases": assignments.exclude(release_disposition="").count(),
        "events": assignments.count() + assignments.exclude(release_disposition="").count(),
        # Multiple open assignments are blocked by a database constraint. Overlap validation
        # remains part of the mutation service; the large-data page no longer rescans every
        # historical segment in JavaScript just to render this health card.
        "integrityIssues": 0,
    }


def _serialize_pool_worker(worker, *, include_commercial: bool = True) -> dict[str, object]:
    payload = serialize_worker(worker, include_commercial=include_commercial)
    history = [item for item in worker.rental_assignments.all() if item.cancelled_at is None]
    last = next((item for item in reversed(history) if item.effective_from <= date.today()), None)
    if last:
        payload["lastProjectId"] = project_public_id(last.project)
        payload["lastProject"] = last.project.name
    else:
        payload["lastProjectId"] = None
        payload["lastProject"] = ""
    return payload


@require_http_methods(["GET"])
@api_workspace_required(Workspace.RENTAL)
def assignment_project_lookup_api(request: HttpRequest) -> JsonResponse:
    """Bounded project lookup for assignment/transfer drawers.

    The drawer never hydrates the project master. Search pages use ``page_size + 1``
    rows instead of COUNT, and the assignment services remain the transactional
    authority for company, lifecycle, effective-date, and current-project rules.
    """
    try:
        _require_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
        effective_date = parse_date(request.GET.get("effective_date"), "effective_date")
        query = str(request.GET.get("q", "")).strip()
        exclude_project_id = str(request.GET.get("exclude_project_id", "")).strip()
        try:
            page = max(1, int(request.GET.get("page", 1) or 1))
            page_size = min(25, max(5, int(request.GET.get("page_size", 10) or 10)))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page": "page and page_size must be integers."}) from exc

        if len(query) < 2:
            return JsonResponse({
                "ok": True,
                "results": [],
                "limit": 25,
                "requiresQuery": True,
                "meta": {"page": 1, "pageSize": page_size, "hasNext": False, "hasPrevious": False},
            })

        rows = restrict_projects((
            rental_projects_for_company(company=request.company, query=query, status=ProjectStatus.ACTIVE)
            .filter(archived_at__isnull=True, deleted_at__isnull=True)
            .filter(Q(start_date__isnull=True) | Q(start_date__lte=effective_date))
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=effective_date))
            .order_by("code", "name")
        ), request.company_membership)
        if exclude_project_id:
            try:
                excluded = rental_project_for_company(company=request.company, identifier=exclude_project_id)
            except Project.DoesNotExist:
                excluded = None
            if excluded is not None:
                rows = rows.exclude(pk=excluded.pk)

        start = (page - 1) * page_size
        window = list(rows[start:start + page_size + 1])
        has_next = len(window) > page_size
        window = window[:page_size]
        return JsonResponse({
            "ok": True,
            "results": [{
                "id": project_public_id(project),
                "code": project.code,
                "name": project.name,
                "client": project.client_name,
                "location": project.location,
            } for project in window],
            "limit": 25,
            "requiresQuery": False,
            "meta": {
                "page": page,
                "pageSize": page_size,
                "hasNext": has_next,
                "hasPrevious": page > 1,
            },
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def assignments_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_ASSIGNMENTS_VIEW if request.method == "GET" else AccessPermission.RENTAL_ASSIGNMENTS_MANAGE)
        if request.method == "GET":
            view = str(request.GET.get("view") or "history").strip().lower().replace("-", "_")
            worker_id = request.GET.get("worker_id") or None
            project_id = request.GET.get("project_id") or None
            supplier_id = request.GET.get("supplier_id") or None

            if view == "summary":
                return JsonResponse({"ok": True, "summary": _assignment_summary_payload(company=request.company, membership=request.company_membership)})

            if view in {"deployment", "pool"}:
                allowed_sorts = {"worker": "worker_number", "name": "full_name", "supplier": "supplier__name", "status": "status"}
                controls = _bounded_list_controls(request, allowed_sorts=allowed_sorts, default_sort="worker")
                rows = workers_for_company(
                    company=request.company,
                    query=request.GET.get("q", ""),
                    supplier_id=supplier_id,
                    operational_status="assigned" if view == "deployment" else "pool",
                    project_id=(_scoped_project(request, project_id).pk if project_id and view == "deployment" else None),
                    membership=request.company_membership,
                )
                rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
                include_commercial = _commercial_visible(request)
                results, meta = serialize_list(
                    rows,
                    controls=controls,
                    serializer=lambda worker: (
                        serialize_worker(worker, include_commercial=include_commercial)
                        if view == "deployment"
                        else _serialize_pool_worker(worker, include_commercial=include_commercial)
                    ),
                )
                return JsonResponse({"ok": True, "view": view, "results": results, "meta": meta})

            rows = restrict_projects(assignments_for_company(
                company=request.company,
                worker_id=worker_id,
                project_id=project_id,
                supplier_id=supplier_id,
                query=request.GET.get("q", ""),
            ), request.company_membership, field="project_id")
            if view == "activity":
                event_type = str(request.GET.get("event_type") or "").strip().lower().replace("-", "_").replace(" ", "_")
                if event_type in {"project_assignment", "assignment"}:
                    rows = rows.filter(change_type=AssignmentChangeType.ASSIGNMENT)
                elif event_type in {"project_transfer", "transfer"}:
                    rows = rows.filter(change_type=AssignmentChangeType.TRANSFER)
                elif event_type in {"trade_change", "trade"}:
                    rows = rows.filter(change_type=AssignmentChangeType.TRADE_CHANGE)
                elif event_type in {"rate_change", "rate"}:
                    rows = rows.filter(change_type=AssignmentChangeType.RATE_CHANGE)
                elif event_type in {"trade_rate_changes", "trade_rate", "changes"}:
                    rows = rows.filter(change_type__in=[AssignmentChangeType.TRADE_CHANGE, AssignmentChangeType.RATE_CHANGE])
                elif event_type == "release":
                    rows = rows.exclude(release_disposition="")
                elif event_type not in {"", "all", "all_activity"}:
                    raise ValidationError({"event_type": "Unknown assignment activity filter."})

                allowed_sorts = {"effective": "effective_from", "worker": "worker__worker_number", "project": "project__name", "created": "created_at"}
                controls = _bounded_list_controls(request, allowed_sorts=allowed_sorts, default_sort="effective", default_direction="desc")
                rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
                # serialize_list cannot expand a released segment into a second lifecycle
                # event, so page assignment segments first and expand only the bounded page.
                from django.core.paginator import Paginator
                paginator = Paginator(rows, controls.page_size)
                page_obj = paginator.get_page(controls.page)
                segments = list(page_obj.object_list)
                results = serialized_assignment_activity(company=request.company, assignments=segments, event_filter=event_type, include_commercial=_commercial_visible(request))
                return JsonResponse({
                    "ok": True,
                    "view": "activity",
                    "results": results,
                    "meta": {
                        "count": paginator.count,
                        "page": page_obj.number,
                        "pageSize": controls.page_size,
                        "totalPages": paginator.num_pages,
                        "sort": controls.sort,
                        "direction": controls.direction,
                        "returnedEvents": len(results),
                    },
                })

            rows = list(rows)
            return JsonResponse({
                "ok": True,
                "results": serialized_assignment_history(company=request.company, assignments=rows, include_commercial=_commercial_visible(request)),
            })

        body = json_body(request)
        action = str(body.get("action") or "").strip().lower().replace("-", "_").replace(" ", "_")
        worker_id = body.get("worker_id")
        if not worker_id:
            raise ValidationError({"worker_id": "worker_id is required."})
        reason = str(body.get("reason") or "").strip()
        effective_date = None if action == "cancel" else parse_date(body.get("effective_date"), "effective_date")

        if action == "assign":
            if not body.get("project_id"):
                raise ValidationError({"project_id": "project_id is required."})
            assignment = assign_worker(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                project_id=body.get("project_id"),
                trade=str(body.get("trade") or ""),
                rate_type=str(body.get("rate_type") or ""),
                rate=body.get("rate"),
                effective_date=effective_date,
                reason=reason,
                request=request,
            )
        elif action == "transfer":
            if not body.get("project_id"):
                raise ValidationError({"project_id": "project_id is required."})
            assignment = transfer_worker(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                project_id=body.get("project_id"),
                trade=str(body.get("trade") or ""),
                rate_type=str(body.get("rate_type") or ""),
                rate=body.get("rate"),
                effective_date=effective_date,
                reason=reason,
                request=request,
            )
        elif action in {"trade", "trade_change"}:
            assignment = change_worker_trade(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                trade=str(body.get("trade") or ""),
                rate_type=str(body.get("rate_type") or "") or None,
                rate=body.get("rate"),
                effective_date=effective_date,
                reason=reason,
                request=request,
            )
        elif action in {"rate", "rate_change"}:
            assignment = change_worker_rate(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                rate_type=str(body.get("rate_type") or ""),
                rate=body.get("rate"),
                effective_date=effective_date,
                reason=reason,
                request=request,
            )
        elif action == "release":
            assignment = release_worker(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                effective_date=effective_date,
                disposition=str(body.get("disposition") or "Available"),
                reason=reason,
                note=str(body.get("note") or ""),
                request=request,
            )
        elif action == "cancel":
            assignment = cancel_scheduled_assignment(
                actor_membership=request.company_membership,
                worker_id=worker_id,
                reason=reason,
                request=request,
            )
        else:
            raise ValidationError({"action": "Action must be assign, transfer, trade, rate, release, or cancel."})

        payload = _assignment_worker_payload(company=request.company, worker_id=worker_id, membership=request.company_membership)
        payload.update({"ok": True, "assignmentId": str(assignment.pk)})
        return JsonResponse(payload, status=201 if action == "assign" else 200)
    except Exception as exc:
        return handle_api_error(exc)

from datetime import date as _date
from .selectors.timesheets import rental_timesheet_context, rental_timesheet_summary, _period_payload
from .models import RentalTimesheetEntry, RentalTimesheetOvertime
from .services.timesheets import save_entries as save_rental_timesheet_entries, save_overtime as save_rental_timesheet_overtime, transition_timesheet as transition_rental_timesheet


def _period_start_value(value):
    parsed = parse_date(value, "period")
    return parsed.replace(day=1)


def _bounded_timesheet_page(request: HttpRequest) -> tuple[int, int]:
    try:
        page = max(1, int(request.GET.get("page") or 1))
        page_size = int(request.GET.get("page_size") or 50)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"page": "page and page_size must be positive integers."}) from exc
    if page_size not in {25, 50, 100}:
        raise ValidationError({"page_size": "page_size must be 25, 50, or 100."})
    return page, page_size


def _rental_header_delta(*, request: HttpRequest, period) -> dict[str, object]:
    project = period.project
    return {
        "deltaOnly": True,
        "period": _period_payload(
            period=period, project=project, start=period.period_start, end=period.period_end,
            membership=request.company_membership,
        ),
        "summary": rental_timesheet_summary(
            company=request.company, project=project, period=period,
            start=period.period_start, end=period.period_end,
        ),
    }


def _rental_entry_delta(*, request: HttpRequest, period, raw_rows: list[dict[str, object]]) -> dict[str, object]:
    requested: list[tuple[str, date]] = []
    for row in raw_rows:
        worker_id = str(row.get("worker_id") or "")
        work_date = row.get("work_date")
        if not isinstance(work_date, date):
            work_date = parse_date(work_date, "work_date")
        requested.append((worker_id, work_date))
    worker_ids = {worker_id for worker_id, _work_date in requested}
    work_dates = {work_date for _worker_id, work_date in requested}
    saved = {
        (str(row.worker_id), row.work_date): (
            row.code or (str(int(row.regular_hours)) if row.regular_hours == row.regular_hours.to_integral() else format(row.regular_hours.normalize(), "f"))
        )
        for row in RentalTimesheetEntry.objects.for_company(request.company).filter(
            period=period, worker_id__in=worker_ids, work_date__in=work_dates
        )
    }
    payload = _rental_header_delta(request=request, period=period)
    payload["changes"] = [
        {"workerId": worker_id, "day": work_date.day, "value": saved.get((worker_id, work_date), "")}
        for worker_id, work_date in requested
    ]
    return payload


def _rental_overtime_delta(*, request: HttpRequest, period, worker_id: str) -> dict[str, object]:
    row = RentalTimesheetOvertime.objects.for_company(request.company).filter(period=period, worker_id=worker_id).first()
    payload = _rental_header_delta(request=request, period=period)
    include_commercial = _commercial_visible(request)
    payload["overtime"] = {
        worker_id: (
            {"hours": str(row.hours), "rate": str(row.rate) if include_commercial else None, "trade": row.trade, "rateType": row.rate_type}
            if row else {"hours": "0", "rate": None if not include_commercial else "0", "trade": "", "rateType": ""}
        )
    }
    return payload


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheets_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_TIMESHEETS_VIEW if request.method == "GET" else AccessPermission.RENTAL_TIMESHEETS_EDIT)
        if request.method == "GET":
            project_id = request.GET.get("project_id")
            if not project_id:
                raise ValidationError({"project_id": "project_id is required."})
            period_start = _period_start_value(request.GET.get("period"))
            page, page_size = _bounded_timesheet_page(request)
            return JsonResponse({
                "ok": True,
                **rental_timesheet_context(
                    company=request.company,
                    project_id=project_id,
                    period_start=period_start,
                    membership=request.company_membership,
                    query=request.GET.get("q", ""),
                    supplier_id=request.GET.get("supplier_id", ""),
                    page=page,
                    page_size=page_size,
                    include_summary=request.GET.get("summary", "1") != "0",
                ),
            })
        body = json_body(request)
        project_id = body.get("project_id")
        if not project_id:
            raise ValidationError({"project_id": "project_id is required."})
        period_start = _period_start_value(body.get("period"))
        rows = body.get("entries")
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"entries": "entries must be a non-empty array."})
        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError({"entries": "Each entry must be an object."})
            normalized.append({
                "worker_id": row.get("worker_id"),
                "work_date": parse_date(row.get("work_date"), "work_date"),
                "value": row.get("value", ""),
                "note": row.get("note", ""),
            })
        period = save_rental_timesheet_entries(
            actor_membership=request.company_membership,
            project_id=project_id,
            period_start=period_start,
            entries=normalized,
            request=request,
        )
        return JsonResponse({"ok": True, **_rental_entry_delta(request=request, period=period, raw_rows=normalized)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheet_overtime_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_OVERTIME_EDIT)
        body = json_body(request)
        project_id = body.get("project_id")
        worker_id = str(body.get("worker_id") or "")
        if not project_id or not worker_id:
            raise ValidationError("project_id and worker_id are required.")
        period_start = _period_start_value(body.get("period"))
        period = save_rental_timesheet_overtime(
            actor_membership=request.company_membership,
            project_id=project_id,
            period_start=period_start,
            worker_id=worker_id,
            hours=body.get("hours", 0),
            rate=body.get("rate"),
            request=request,
        )
        return JsonResponse({"ok": True, **_rental_overtime_delta(request=request, period=period, worker_id=worker_id)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheet_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        action_name = normalize_attendance_workflow_action(body.get("action"))
        _require_permission(
            request,
            AccessPermission.RENTAL_TIMESHEETS_SUBMIT if action_name == "submit" else AccessPermission.RENTAL_TIMESHEETS_APPROVE,
        )
        project_id = body.get("project_id")
        if not project_id:
            raise ValidationError({"project_id": "project_id is required."})
        period_start = _period_start_value(body.get("period"))
        period = transition_rental_timesheet(
            actor_membership=request.company_membership,
            project_id=project_id,
            period_start=period_start,
            action=str(body.get("action") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
        return JsonResponse({"ok": True, **_rental_header_delta(request=request, period=period)})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET"])
@api_workspace_required(Workspace.RENTAL)
def rental_settlements_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_SETTLEMENTS_VIEW)
        period_start = _request_period(request)
        detail = str(request.GET.get("detail", "")).strip().lower() in {"1", "true", "yes"}
        project_id = request.GET.get("project_id") or None
        if detail and not project_id:
            raise ValidationError({"project_id": "project_id is required for settlement detail."})
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(
                company=request.company,
                period_start=period_start,
                membership=request.company_membership,
                project_id=project_id,
                supplier_id=request.GET.get("supplier_id") or None,
                include_rows=detail,
                include_adjustments=False,
                include_payments=not detail,
            ),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_settlements_calculate_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_SETTLEMENTS_PREPARE)
        body = json_body(request)
        period_start = _request_period(request, body)
        project_id = body.get("project_id")
        if not project_id:
            raise ValidationError({"project_id": "project_id is required."})
        calculate_project_settlements(
            actor_membership=request.company_membership,
            project_id=project_id,
            period_start=period_start,
            request=request,
        )
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_settlements_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body = json_body(request)
        settlement_action = str(body.get("action") or "").strip().lower().replace("-", "_")
        _require_permission(
            request,
            AccessPermission.RENTAL_SETTLEMENTS_APPROVE if settlement_action in {"approve", "return_to_draft", "lock"} else AccessPermission.RENTAL_SETTLEMENTS_PREPARE,
        )
        period_start = _request_period(request, body)
        project_id = body.get("project_id")
        if not project_id:
            raise ValidationError({"project_id": "project_id is required."})
        transition_project_settlements(
            actor_membership=request.company_membership,
            project_id=project_id,
            period_start=period_start,
            action=str(body.get("action") or ""),
            reason=str(body.get("reason") or ""),
            confirmed=body.get("confirmed") is True,
            request=request,
        )
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
        })
    except Exception as exc:
        return handle_api_error(exc)




@require_http_methods(["GET"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustment_lookup_api(request: HttpRequest) -> JsonResponse:
    """Bounded, assignment-aware combobox lookup for rental adjustments.

    Worker and project options are intentionally queried in small pages instead of
    serializing either master directory.  The endpoint avoids an exact COUNT query:
    every page reads ``page_size + 1`` rows and exposes ``hasNext``.  The create
    service remains the final transactional authority for company/lifecycle/date
    validation.
    """
    try:
        _require_permission(request, AccessPermission.RENTAL_ADJUSTMENTS_MANAGE)
        mode = str(request.GET.get("mode", "workers")).strip().lower()
        if mode not in {"workers", "projects"}:
            raise ValidationError({"mode": "mode must be workers or projects."})
        transaction_date = parse_date(request.GET.get("transaction_date"), "transaction_date")
        query = str(request.GET.get("q", "")).strip()
        worker_id = str(request.GET.get("worker_id", "")).strip()
        project_id = str(request.GET.get("project_id", "")).strip()

        try:
            page = max(1, int(request.GET.get("page", 1) or 1))
            page_size = min(25, max(5, int(request.GET.get("page_size", 10) or 10)))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page": "page and page_size must be integers."}) from exc

        def page_payload(queryset, serializer):
            start = (page - 1) * page_size
            window = list(queryset[start : start + page_size + 1])
            has_next = len(window) > page_size
            window = window[:page_size]
            return {
                "ok": True,
                "results": [serializer(item) for item in window],
                "limit": 25,
                "meta": {
                    "page": page,
                    "pageSize": page_size,
                    "hasNext": has_next,
                    "hasPrevious": page > 1,
                },
            }

        if mode == "workers":
            assignments = restrict_projects((
                WorkerAssignment.objects.for_company(request.company)
                .filter(worker_id=OuterRef("pk"), cancelled_at__isnull=True, effective_from__lte=transaction_date)
                .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=transaction_date))
                .filter(project__status=ProjectStatus.ACTIVE, project__deleted_at__isnull=True)
                .filter(Q(project__start_date__isnull=True) | Q(project__start_date__lte=transaction_date))
                .filter(Q(project__end_date__isnull=True) | Q(project__end_date__gte=transaction_date))
            ), request.company_membership, field="project_id")
            rows = (
                RentalWorker.objects.for_company(request.company)
                .select_related("supplier")
                .filter(
                    deleted_at__isnull=True,
                    archived_at__isnull=True,
                    supplier__deleted_at__isnull=True,
                    supplier__archived_at__isnull=True,
                )
                .annotate(_has_effective_assignment=Exists(assignments))
                .filter(_has_effective_assignment=True)
            )
            if worker_id:
                rows = rows.filter(pk=worker_id)
                page = 1
            elif len(query) < 2:
                return JsonResponse({
                    "ok": True,
                    "results": [],
                    "limit": 25,
                    "requiresQuery": True,
                    "meta": {"page": 1, "pageSize": page_size, "hasNext": False, "hasPrevious": False},
                })
            if query:
                rows = rows.filter(
                    Q(worker_number__icontains=query)
                    | Q(full_name__icontains=query)
                    | Q(national_id__icontains=query)
                    | Q(supplier__code__icontains=query)
                    | Q(supplier__name__icontains=query)
                )
            payload = page_payload(
                rows.order_by("worker_number", "full_name"),
                lambda worker: {
                    "id": str(worker.pk),
                    "code": worker.worker_number,
                    "name": worker.full_name,
                    "supplierId": str(worker.supplier_id),
                    "supplierCode": worker.supplier.code,
                    "supplier": worker.supplier.name,
                },
            )
            payload["requiresQuery"] = False
            return JsonResponse(payload)

        if not worker_id:
            return JsonResponse({
                "ok": True,
                "results": [],
                "limit": 25,
                "requiresWorker": True,
                "meta": {"page": 1, "pageSize": page_size, "hasNext": False, "hasPrevious": False},
            })
        assignments = restrict_projects((
            WorkerAssignment.objects.for_company(request.company)
            .select_related("project", "worker", "worker__supplier")
            .filter(
                worker_id=worker_id,
                cancelled_at__isnull=True,
                effective_from__lte=transaction_date,
                worker__deleted_at__isnull=True,
                worker__archived_at__isnull=True,
                worker__supplier__deleted_at__isnull=True,
                worker__supplier__archived_at__isnull=True,
                project__status=ProjectStatus.ACTIVE,
                project__deleted_at__isnull=True,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=transaction_date))
            .filter(Q(project__start_date__isnull=True) | Q(project__start_date__lte=transaction_date))
            .filter(Q(project__end_date__isnull=True) | Q(project__end_date__gte=transaction_date))
        ), request.company_membership, field="project_id")
        if project_id:
            project = _scoped_project(request, project_id)
            assignments = assignments.filter(project_id=project.pk)
            page = 1
        if query:
            assignments = assignments.filter(
                Q(project__code__icontains=query)
                | Q(project__name__icontains=query)
                | Q(project__client_name__icontains=query)
                | Q(project__location__icontains=query)
            )
        payload = page_payload(
            assignments.order_by("project__code", "-effective_from", "-created_at"),
            lambda item: {
                "id": project_public_id(item.project),
                "code": item.project.code,
                "name": item.project.name,
                "client": item.project.client_name,
                "location": item.project.location,
                "assignmentId": str(item.pk),
                "trade": item.trade,
                "supplierId": str(item.worker.supplier_id),
                "supplierCode": item.worker.supplier.code,
                "supplier": item.worker.supplier.name,
            },
        )
        payload["requiresWorker"] = False
        return JsonResponse(payload)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustments_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_ADJUSTMENTS_VIEW if request.method == "GET" else AccessPermission.RENTAL_ADJUSTMENTS_MANAGE)
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse({
                "ok": True,
                **rental_adjustment_page_context(
                    company=request.company,
                    period_start=period_start,
                    membership=request.company_membership,
                    page=request.GET.get("page", 1),
                    page_size=request.GET.get("page_size", 50),
                    search=str(request.GET.get("search") or ""),
                    adjustment_type=str(request.GET.get("type") or "All"),
                    status=str(request.GET.get("status") or "All"),
                    project_id=str(request.GET.get("project") or ""),
                    supplier_id=str(request.GET.get("supplier") or ""),
                    project_search=str(request.GET.get("project_search") or ""),
                    supplier_search=str(request.GET.get("supplier_search") or ""),
                ),
            })
        body = json_body(request)
        period_start = _request_period(request, body)
        adjustment = create_rental_adjustment(
            actor_membership=request.company_membership,
            worker_id=body.get("worker_id"),
            project_id=body.get("project_id"),
            transaction_date=parse_date(body.get("transaction_date"), "transaction_date"),
            period_start=period_start,
            adjustment_type=str(body.get("adjustment_type") or ""),
            amount=_decimal(body.get("amount"), "amount"),
            reason=str(body.get("reason") or ""),
            reference=str(body.get("reference") or ""),
            request=request,
        )
        adjustment = (
            RentalAdjustment.objects.for_company(request.company)
            .select_related("project", "submitted_by", "approved_by")
            .get(pk=adjustment.pk)
        )
        return JsonResponse({
            "ok": True,
            "period": f"{period_start:%Y-%m}",
            "adjustment": serialize_rental_adjustment(adjustment),
        }, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustment_detail_api(request: HttpRequest, adjustment_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_ADJUSTMENTS_MANAGE)
        body = json_body(request)
        current = RentalAdjustment.objects.for_company(request.company).get(pk=adjustment_id)
        changes = {}
        for key in ("adjustment_type", "amount", "reason", "reference"):
            if key in body:
                changes[key] = body.get(key)
        adjustment = update_rental_adjustment(
            actor_membership=request.company_membership,
            adjustment_id=adjustment_id,
            request=request,
            **changes,
        )
        adjustment = (
            RentalAdjustment.objects.for_company(request.company)
            .select_related("project", "submitted_by", "approved_by")
            .get(pk=adjustment.pk)
        )
        return JsonResponse({
            "ok": True,
            "period": f"{current.period_start:%Y-%m}",
            "adjustment": serialize_rental_adjustment(adjustment),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustment_workflow_api(request: HttpRequest, adjustment_id) -> JsonResponse:
    try:
        body = json_body(request)
        adjustment_action = str(body.get("action") or "").strip().lower().replace("-", "_")
        _require_permission(
            request,
            AccessPermission.RENTAL_ADJUSTMENTS_APPROVE if adjustment_action in {"approve", "reject"} else AccessPermission.RENTAL_ADJUSTMENTS_MANAGE,
        )
        current = RentalAdjustment.objects.for_company(request.company).get(pk=adjustment_id)
        adjustment = transition_rental_adjustment(
            actor_membership=request.company_membership,
            adjustment_id=adjustment_id,
            action=str(body.get("action") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
        adjustment = (
            RentalAdjustment.objects.for_company(request.company)
            .select_related("project", "submitted_by", "approved_by")
            .get(pk=adjustment.pk)
        )
        return JsonResponse({
            "ok": True,
            "period": f"{current.period_start:%Y-%m}",
            "adjustment": serialize_rental_adjustment(adjustment),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def supplier_payments_api(request: HttpRequest) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_PAYMENTS_VIEW if request.method == "GET" else AccessPermission.RENTAL_PAYMENTS_EXECUTE)
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse({
                "ok": True,
                **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
            })
        body = json_body(request)
        settlement_id = body.get("settlement_id")
        if not settlement_id:
            raise ValidationError({"settlement_id": "settlement_id is required."})
        payment = record_supplier_payment(
            actor_membership=request.company_membership,
            settlement_id=settlement_id,
            payment_date=parse_date(body.get("payment_date"), "payment_date"),
            method=str(body.get("method") or ""),
            amount=_decimal(body.get("amount"), "amount"),
            status=str(body.get("status") or "processing"),
            transaction_reference=str(body.get("transaction_reference") or ""),
            note=str(body.get("note") or ""),
            request=request,
        )
        period_start = payment.allocations.select_related("settlement").first().settlement.period_start
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
        }, status=201)
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def supplier_payment_result_api(request: HttpRequest, payment_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_PAYMENTS_EXECUTE)
        body = json_body(request)
        payment = transition_supplier_payment(
            actor_membership=request.company_membership,
            payment_id=payment_id,
            status=str(body.get("status") or ""),
            transaction_reference=str(body.get("transaction_reference") or ""),
            reason=str(body.get("reason") or ""),
            request=request,
        )
        allocation = payment.allocations.select_related("settlement").first()
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(company=request.company, period_start=allocation.settlement.period_start, membership=request.company_membership),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def supplier_payment_retry_api(request: HttpRequest, payment_id) -> JsonResponse:
    try:
        _require_permission(request, AccessPermission.RENTAL_PAYMENTS_EXECUTE)
        body = json_body(request)
        retry = retry_supplier_payment(
            actor_membership=request.company_membership,
            payment_id=payment_id,
            payment_date=parse_optional_date(body.get("payment_date"), "payment_date"),
            request=request,
        )
        allocation = retry.allocations.select_related("settlement").first()
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(company=request.company, period_start=allocation.settlement.period_start, membership=request.company_membership),
        }, status=201)
    except Exception as exc:
        return handle_api_error(exc)
