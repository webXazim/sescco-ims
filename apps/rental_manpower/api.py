from __future__ import annotations

from apps.projects.contracts import ProjectStatus
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id
from apps.projects.services import archive_project, restore_project_archive, trash_unused_project, restore_project_trash

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.core.query_controls import ListControls, apply_ordering, parse_list_controls, serialize_list
from apps.rental_manpower.api_utils import handle_api_error, json_body, parse_date, parse_optional_date
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    RentalAdjustment,
    AssignmentChangeType,
    WorkerAssignment,
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
    rental_adjustment_page_context,
    rental_settlement_context,
    rental_financial_metrics_for_period,
    serialize_rental_adjustment,
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


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def suppliers_api(request: HttpRequest) -> JsonResponse:
    try:
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
                project_pk = rental_project_for_company(company=request.company, identifier=project_id).pk
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
            if payment_terms_blank:
                rows = rows.filter(payment_terms="")
            period_raw = str(request.GET.get("period", "")).strip()
            metrics = rental_financial_metrics_for_period(company=request.company, period_start=_period_start(period_raw)) if period_raw else {"suppliers": {}}
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
                client=client, manager=manager, supplier_id=supplier_id,
            )
            period_raw = str(request.GET.get("period", "")).strip()
            metrics = rental_financial_metrics_for_period(company=request.company, period_start=_period_start(period_raw)) if period_raw else {"projects": {}}
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            project_metrics = metrics.get("projects", {})
            results, meta = serialize_list(
                rows, controls=controls,
                serializer=lambda item: serialize_project(item, project_metrics.get(str(item.reference))),
            )
            return JsonResponse({"ok": True, "results": results, "meta": meta})
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
                project_pk = rental_project_for_company(company=request.company, identifier=project_raw).pk
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
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_worker)
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
        if request.method == "GET":
            worker = workers_for_company(company=request.company, archived=None).get(pk=worker_id)
            assignments = list(assignments_for_company(company=request.company, worker_id=worker_id))
            return JsonResponse({
                "ok": True,
                "worker": serialize_worker(worker),
                "assignments": serialized_assignment_history(company=request.company, assignments=assignments),
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



def _assignment_worker_payload(*, company, worker_id):
    worker = workers_for_company(company=company).get(pk=worker_id)
    assignments = list(assignments_for_company(company=company, worker_id=worker_id))
    return {
        "worker": serialize_worker(worker),
        "assignments": serialized_assignment_history(company=company, assignments=assignments),
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


def _assignment_summary_payload(*, company) -> dict[str, int]:
    assignments = WorkerAssignment.objects.for_company(company)
    return {
        "assigned": workers_for_company(company=company, operational_status="assigned").count(),
        "available": workers_for_company(company=company, operational_status="available").count(),
        "transfers": assignments.filter(change_type=AssignmentChangeType.TRANSFER).count(),
        "changes": assignments.filter(change_type__in=[AssignmentChangeType.TRADE_CHANGE, AssignmentChangeType.RATE_CHANGE]).count(),
        "releases": assignments.exclude(release_disposition="").count(),
        "events": assignments.count() + assignments.exclude(release_disposition="").count(),
        # Multiple open assignments are blocked by a database constraint. Overlap validation
        # remains part of the mutation service; the large-data page no longer rescans every
        # historical segment in JavaScript just to render this health card.
        "integrityIssues": 0,
    }


def _serialize_pool_worker(worker) -> dict[str, object]:
    payload = serialize_worker(worker)
    history = [item for item in worker.rental_assignments.all() if item.cancelled_at is None]
    last = next((item for item in reversed(history) if item.effective_from <= date.today()), None)
    if last:
        payload["lastProjectId"] = project_public_id(last.project)
        payload["lastProject"] = last.project.name
    else:
        payload["lastProjectId"] = None
        payload["lastProject"] = ""
    return payload


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def assignments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            view = str(request.GET.get("view") or "history").strip().lower().replace("-", "_")
            worker_id = request.GET.get("worker_id") or None
            project_id = request.GET.get("project_id") or None
            supplier_id = request.GET.get("supplier_id") or None

            if view == "summary":
                return JsonResponse({"ok": True, "summary": _assignment_summary_payload(company=request.company)})

            if view in {"deployment", "pool"}:
                allowed_sorts = {"worker": "worker_number", "name": "full_name", "supplier": "supplier__name", "status": "status"}
                controls = _bounded_list_controls(request, allowed_sorts=allowed_sorts, default_sort="worker")
                rows = workers_for_company(
                    company=request.company,
                    query=request.GET.get("q", ""),
                    supplier_id=supplier_id,
                    operational_status="assigned" if view == "deployment" else "pool",
                    project_id=(rental_project_for_company(company=request.company, identifier=project_id).pk if project_id and view == "deployment" else None),
                )
                rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
                results, meta = serialize_list(
                    rows,
                    controls=controls,
                    serializer=serialize_worker if view == "deployment" else _serialize_pool_worker,
                )
                return JsonResponse({"ok": True, "view": view, "results": results, "meta": meta})

            rows = assignments_for_company(
                company=request.company,
                worker_id=worker_id,
                project_id=project_id,
                supplier_id=supplier_id,
                query=request.GET.get("q", ""),
            )
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
                results = serialized_assignment_activity(company=request.company, assignments=segments, event_filter=event_type)
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
                "results": serialized_assignment_history(company=request.company, assignments=rows),
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

        payload = _assignment_worker_payload(company=request.company, worker_id=worker_id)
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
    payload["overtime"] = {
        worker_id: (
            {"hours": str(row.hours), "rate": str(row.rate), "trade": row.trade, "rateType": row.rate_type}
            if row else {"hours": "0", "rate": "0", "trade": "", "rateType": ""}
        )
    }
    return payload


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheets_api(request: HttpRequest) -> JsonResponse:
    try:
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
        period_start = _request_period(request)
        return JsonResponse({
            "ok": True,
            **rental_settlement_context(
                company=request.company,
                period_start=period_start,
                membership=request.company_membership,
                project_id=request.GET.get("project_id") or None,
                supplier_id=request.GET.get("supplier_id") or None,
            ),
        })
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_settlements_calculate_api(request: HttpRequest) -> JsonResponse:
    try:
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
    """Bounded, assignment-aware owner/project lookup for the rental adjustment drawer.

    This endpoint deliberately returns compact selector rows rather than serializing the
    full worker/project masters.  Results are company-scoped, lifecycle-safe, capped at
    25 rows, and constrained to an assignment effective on ``transaction_date``.  The
    create service remains the final transactional authority.
    """
    try:
        mode = str(request.GET.get("mode", "workers")).strip().lower()
        if mode not in {"workers", "projects"}:
            raise ValidationError({"mode": "mode must be workers or projects."})
        transaction_date = parse_date(request.GET.get("transaction_date"), "transaction_date")
        query = str(request.GET.get("q", "")).strip()
        worker_id = str(request.GET.get("worker_id", "")).strip()

        if mode == "workers":
            assignments = (
                WorkerAssignment.objects.for_company(request.company)
                .filter(worker_id=OuterRef("pk"), cancelled_at__isnull=True, effective_from__lte=transaction_date)
                .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=transaction_date))
                .filter(
                    project__status=ProjectStatus.ACTIVE,
                    project__deleted_at__isnull=True,
                )
                .filter(Q(project__start_date__isnull=True) | Q(project__start_date__lte=transaction_date))
                .filter(Q(project__end_date__isnull=True) | Q(project__end_date__gte=transaction_date))
            )
            rows = (
                RentalWorker.objects.for_company(request.company)
                .select_related("supplier")
                .filter(
                    deleted_at__isnull=True, archived_at__isnull=True,
                    supplier__deleted_at__isnull=True, supplier__archived_at__isnull=True,
                )
                .annotate(_has_effective_assignment=Exists(assignments))
                .filter(_has_effective_assignment=True)
            )
            if worker_id:
                rows = rows.filter(pk=worker_id)
            elif len(query) < 2:
                return JsonResponse({"ok": True, "results": [], "limit": 25, "requiresQuery": True})
            if query:
                rows = rows.filter(
                    Q(worker_number__icontains=query)
                    | Q(full_name__icontains=query)
                    | Q(national_id__icontains=query)
                    | Q(supplier__code__icontains=query)
                    | Q(supplier__name__icontains=query)
                )
            results = [
                {
                    "id": str(worker.pk),
                    "code": worker.worker_number,
                    "name": worker.full_name,
                    "supplierId": str(worker.supplier_id),
                    "supplierCode": worker.supplier.code,
                    "supplier": worker.supplier.name,
                }
                for worker in rows.order_by("worker_number", "full_name")[:25]
            ]
            return JsonResponse({"ok": True, "results": results, "limit": 25, "requiresQuery": False})

        if not worker_id:
            return JsonResponse({"ok": True, "results": [], "limit": 25, "requiresWorker": True})
        assignments = (
            WorkerAssignment.objects.for_company(request.company)
            .select_related("project", "worker", "worker__supplier")
            .filter(
                worker_id=worker_id, cancelled_at__isnull=True, effective_from__lte=transaction_date,
                worker__deleted_at__isnull=True, worker__archived_at__isnull=True,
                worker__supplier__deleted_at__isnull=True, worker__supplier__archived_at__isnull=True,
                project__status=ProjectStatus.ACTIVE, project__deleted_at__isnull=True,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=transaction_date))
            .filter(Q(project__start_date__isnull=True) | Q(project__start_date__lte=transaction_date))
            .filter(Q(project__end_date__isnull=True) | Q(project__end_date__gte=transaction_date))
        )
        if query:
            assignments = assignments.filter(
                Q(project__code__icontains=query)
                | Q(project__name__icontains=query)
                | Q(project__client_name__icontains=query)
                | Q(project__location__icontains=query)
            )
        results = [
            {
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
            }
            for item in assignments.order_by("project__code", "-effective_from", "-created_at")[:25]
        ]
        return JsonResponse({"ok": True, "results": results, "limit": 25, "requiresWorker": False})
    except Exception as exc:
        return handle_api_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustments_api(request: HttpRequest) -> JsonResponse:
    try:
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
