from __future__ import annotations

from apps.projects.contracts import ProjectStatus
from apps.rental_manpower.project_adapter import rental_project_for_company
from apps.projects.services import archive_project, restore_project_archive, trash_unused_project, restore_project_trash

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.core.query_controls import apply_ordering, parse_list_controls, serialize_list
from apps.rental_manpower.api_utils import handle_api_error, json_body, parse_date, parse_optional_date
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    RentalAdjustment,
)
from apps.rental_manpower.selectors import (
    assignments_for_company,
    serialized_assignment_history,
    projects_for_company,
    serialize_project,
    serialize_supplier,
    serialize_worker,
    suppliers_for_company,
    workers_for_company,
    rental_settlement_context,
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
            rows = suppliers_for_company(company=request.company, query=request.GET.get("q", ""), status=status, archived=_archived_query(request.GET.get("archived", "")))
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_supplier)
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
        if action == "archive": supplier=archive_supplier(actor_membership=request.company_membership, supplier_id=supplier_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore","restore_archive"}: supplier=restore_supplier_archive(actor_membership=request.company_membership, supplier_id=supplier_id, reason=str(body.get("reason", "")), request=request)
        elif action == "restore_trash": supplier=restore_supplier_trash(actor_membership=request.company_membership, supplier_id=supplier_id, request=request)
        elif action in {"deactivate","inactive","activate","reactivate","active"}: supplier=change_supplier_lifecycle(actor_membership=request.company_membership, supplier_id=supplier_id, action=action, reason=str(body.get("reason", "")), request=request)
        else: raise ValidationError({"action":"Supplier lifecycle action must be deactivate, activate, archive, restore archive, or restore trash."})
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
            rows = projects_for_company(company=request.company, query=request.GET.get("q", ""), status=status)
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_project)
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
            status = _status_query(request.GET.get("status", ""), {item.value for item in RentalWorkerStatus})
            supplier_id = request.GET.get("supplier_id") or None
            allowed_sorts = {
                "worker": "worker_number",
                "name": "full_name",
                "supplier": "supplier__name",
                "status": "status",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="worker")
            rows = workers_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                status=status,
                supplier_id=supplier_id,
                archived=_archived_query(request.GET.get("archived", "")),
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


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.RENTAL)
def worker_detail_api(request: HttpRequest, worker_id) -> JsonResponse:
    try:
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
        worker=workers_for_company(company=request.company, archived=None).get(pk=worker.pk)
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


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def assignments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            worker_id = request.GET.get("worker_id") or None
            project_id = request.GET.get("project_id") or None
            supplier_id = request.GET.get("supplier_id") or None
            rows = list(
                assignments_for_company(
                    company=request.company,
                    worker_id=worker_id,
                    project_id=project_id,
                    supplier_id=supplier_id,
                    query=request.GET.get("q", ""),
                )
            )
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
from .selectors.timesheets import rental_timesheet_context
from .services.timesheets import save_entries as save_rental_timesheet_entries, save_overtime as save_rental_timesheet_overtime, transition_timesheet as transition_rental_timesheet


def _period_start_value(value):
    parsed = parse_date(value, "period")
    return parsed.replace(day=1)


@require_http_methods(["GET", "PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheets_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            project_id = request.GET.get("project_id")
            if not project_id:
                raise ValidationError({"project_id": "project_id is required."})
            period_start = _period_start_value(request.GET.get("period"))
            return JsonResponse({"ok": True, **rental_timesheet_context(company=request.company, project_id=project_id, period_start=period_start, membership=request.company_membership)})
        body=json_body(request); project_id=body.get("project_id")
        if not project_id: raise ValidationError({"project_id":"project_id is required."})
        period_start=_period_start_value(body.get("period")); rows=body.get("entries")
        if not isinstance(rows,list) or not rows: raise ValidationError({"entries":"entries must be a non-empty array."})
        normalized=[]
        for row in rows:
            if not isinstance(row,dict): raise ValidationError({"entries":"Each entry must be an object."})
            normalized.append({'worker_id':row.get('worker_id'),'work_date':parse_date(row.get('work_date'),'work_date'),'value':row.get('value',''),'note':row.get('note','')})
        save_rental_timesheet_entries(actor_membership=request.company_membership,project_id=project_id,period_start=period_start,entries=normalized,request=request)
        return JsonResponse({"ok":True,**rental_timesheet_context(company=request.company,project_id=project_id,period_start=period_start,membership=request.company_membership)})
    except Exception as exc: return handle_api_error(exc)


@require_http_methods(["PATCH"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheet_overtime_api(request: HttpRequest) -> JsonResponse:
    try:
        body=json_body(request); project_id=body.get('project_id'); worker_id=body.get('worker_id')
        if not project_id or not worker_id: raise ValidationError("project_id and worker_id are required.")
        period_start=_period_start_value(body.get('period'))
        save_rental_timesheet_overtime(actor_membership=request.company_membership,project_id=project_id,period_start=period_start,worker_id=worker_id,hours=body.get('hours',0),rate=body.get('rate'),request=request)
        return JsonResponse({"ok":True,**rental_timesheet_context(company=request.company,project_id=project_id,period_start=period_start,membership=request.company_membership)})
    except Exception as exc: return handle_api_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_timesheet_workflow_api(request: HttpRequest) -> JsonResponse:
    try:
        body=json_body(request); project_id=body.get('project_id')
        if not project_id: raise ValidationError({"project_id":"project_id is required."})
        period_start=_period_start_value(body.get('period'))
        transition_rental_timesheet(actor_membership=request.company_membership,project_id=project_id,period_start=period_start,action=str(body.get('action') or ''),reason=str(body.get('reason') or ''),request=request)
        return JsonResponse({"ok":True,**rental_timesheet_context(company=request.company,project_id=project_id,period_start=period_start,membership=request.company_membership)})
    except Exception as exc: return handle_api_error(exc)


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


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.RENTAL)
def rental_adjustments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            period_start = _request_period(request)
            return JsonResponse({
                "ok": True,
                **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
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
        return JsonResponse({
            "ok": True,
            "adjustment": serialize_rental_adjustment(adjustment),
            **rental_settlement_context(company=request.company, period_start=period_start, membership=request.company_membership),
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
        return JsonResponse({
            "ok": True,
            "adjustment": serialize_rental_adjustment(adjustment),
            **rental_settlement_context(company=request.company, period_start=current.period_start, membership=request.company_membership),
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
        return JsonResponse({
            "ok": True,
            "adjustment": serialize_rental_adjustment(adjustment),
            **rental_settlement_context(company=request.company, period_start=current.period_start, membership=request.company_membership),
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
