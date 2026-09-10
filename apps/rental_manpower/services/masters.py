from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit
from apps.accounts.roles import Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.contracts import ProjectStatus
from apps.projects.models import Project
from apps.rental_manpower.project_adapter import rental_project_for_company
from apps.core.services.numbering import allocate_number
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalWorker,
    RentalWorkerStatus,
    SupplierStatus,
    WorkerAssignment,
)


def _require_rental_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.RENTAL):
        raise PermissionDenied("Your role cannot modify rental manpower master data.")


def _active_flag(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise ValidationError({"status": "Status must be Active or Inactive."})
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    if normalized in {"active", "true", "1"}:
        return True
    if normalized in {"inactive", "false", "0"}:
        return False
    raise ValidationError({"status": "Status must be Active or Inactive."})


def _supplier_status(value: str | bool) -> str:
    return SupplierStatus.ACTIVE if _active_flag(value) else SupplierStatus.INACTIVE


def _worker_status(value: str | bool) -> str:
    return RentalWorkerStatus.ACTIVE if _active_flag(value) else RentalWorkerStatus.INACTIVE


def _project_status(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError({"status": "Status must be Active, On Hold, Completed, or Archived."})
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "active": ProjectStatus.ACTIVE,
        "on_hold": ProjectStatus.ON_HOLD,
        "completed": ProjectStatus.COMPLETED,
        "archived": ProjectStatus.ARCHIVED,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValidationError({"status": "Status must be Active, On Hold, Completed, or Archived."}) from exc


def _snapshot(obj: Any) -> dict[str, object]:
    if isinstance(obj, ManpowerSupplier):
        return {
            "code": obj.code,
            "name": obj.name,
            "status": obj.status,
            "contact_person": obj.contact_person,
            "phone": obj.phone,
            "email": obj.email,
            "cr_number": obj.cr_number,
            "vat_number": obj.vat_number,
            "payment_terms": obj.payment_terms,
            "address": obj.address,
            "notes": obj.notes,
        }
    if isinstance(obj, Project):
        return {
            "code": obj.code,
            "name": obj.name,
            "client_name": obj.client_name,
            "location": obj.location,
            "start_date": obj.start_date.isoformat() if obj.start_date else None,
            "end_date": obj.end_date.isoformat() if obj.end_date else None,
            "manager_name": obj.manager_name,
            "status": obj.status,
            "notes": obj.notes,
        }
    if isinstance(obj, RentalWorker):
        return {
            "worker_number": obj.worker_number,
            "full_name": obj.full_name,
            "national_id": obj.national_id,
            "phone": obj.phone,
            "supplier_id": str(obj.supplier_id),
            "status": obj.status,
            "notes": obj.notes,
        }
    raise TypeError(f"Unsupported rental master snapshot: {type(obj)!r}")


@transaction.atomic
def create_supplier(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    status: str | bool = SupplierStatus.ACTIVE,
    contact_person: str = "",
    phone: str = "",
    email: str = "",
    cr_number: str = "",
    vat_number: str = "",
    payment_terms: str = "",
    address: str = "",
    notes: str = "",
    request: HttpRequest | None = None,
) -> ManpowerSupplier:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    code = (code or "").strip() or allocate_number(company=company, key="rental.supplier", prefix="SUP-", padding=4)
    supplier = ManpowerSupplier(
        company=company,
        code=code,
        name=name,
        status=_supplier_status(status),
        contact_person=contact_person,
        phone=phone,
        email=email,
        cr_number=cr_number,
        vat_number=vat_number,
        payment_terms=payment_terms,
        address=address,
        notes=notes,
    )
    supplier.full_clean()
    try:
        supplier.save()
    except IntegrityError as exc:
        raise ValidationError("Supplier code, name, CR and VAT number must be unique within the company when provided.") from exc
    record_audit_event(
        company=company,
        area=AuditArea.RENTAL,
        action="rental.supplier.created",
        object_type="rental_manpower.ManpowerSupplier",
        object_id=supplier.pk,
        object_label=str(supplier),
        actor_membership=actor_membership,
        after=_snapshot(supplier),
        request=request,
    )
    return supplier


@transaction.atomic
def update_supplier(
    *,
    actor_membership: CompanyMembership,
    supplier_id,
    code: str,
    name: str,
    status: str | bool,
    contact_person: str = "",
    phone: str = "",
    email: str = "",
    cr_number: str = "",
    vat_number: str = "",
    payment_terms: str = "",
    address: str = "",
    notes: str = "",
    request: HttpRequest | None = None,
) -> ManpowerSupplier:
    _require_rental_edit(actor_membership)
    supplier = ManpowerSupplier.objects.select_for_update().get(pk=supplier_id, company=actor_membership.company)
    before = _snapshot(supplier)
    next_status = _supplier_status(status)
    if supplier.status == SupplierStatus.ACTIVE and next_status == SupplierStatus.INACTIVE:
        if RentalWorker.objects.for_company(supplier.company).filter(supplier=supplier, status=RentalWorkerStatus.ACTIVE).exists():
            raise ValidationError("Deactivate active rental workers before making this supplier inactive.")
    supplier.code = code
    supplier.name = name
    supplier.status = next_status
    supplier.contact_person = contact_person
    supplier.phone = phone
    supplier.email = email
    supplier.cr_number = cr_number
    supplier.vat_number = vat_number
    supplier.payment_terms = payment_terms
    supplier.address = address
    supplier.notes = notes
    supplier.full_clean()
    try:
        supplier.save()
    except IntegrityError as exc:
        raise ValidationError("Supplier code, name, CR and VAT number must be unique within the company when provided.") from exc
    after = _snapshot(supplier)
    if before != after:
        record_audit_event(
            company=supplier.company,
            area=AuditArea.RENTAL,
            action="rental.supplier.updated",
            object_type="rental_manpower.ManpowerSupplier",
            object_id=supplier.pk,
            object_label=str(supplier),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return supplier


def _allocate_project_code(*, company) -> str:
    # Inventory and Rental now share one Project code namespace. The Rental number
    # sequence may start behind pre-existing Inventory project codes, so skip collisions
    # instead of failing a blank-code create with an IntegrityError.
    for _attempt in range(1000):
        candidate = allocate_number(company=company, key="rental.project", prefix="PRJ-", padding=4)
        if not Project.objects.for_company(company).filter(code=candidate).exists():
            return candidate
    raise ValidationError({"code": "Unable to allocate a unique project code."})


@transaction.atomic
def create_project(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    start_date,
    status: str = ProjectStatus.ACTIVE,
    client_name: str = "",
    location: str = "",
    end_date=None,
    manager_name: str = "",
    notes: str = "",
    request: HttpRequest | None = None,
) -> Project:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    code = (code or "").strip() or _allocate_project_code(company=company)
    project = Project(
        company=company,
        code=code,
        name=name,
        client_name=client_name,
        location=location,
        start_date=start_date,
        end_date=end_date,
        manager_name=manager_name,
        status=_project_status(status),
        notes=notes,
        created_by=actor_membership.user,
        updated_by=actor_membership.user,
    )
    project.full_clean()
    try:
        project.save()
    except IntegrityError as exc:
        raise ValidationError("Project code must be unique within the company.") from exc
    record_audit_event(
        company=company,
        area=AuditArea.RENTAL,
        action="rental.project.created",
        object_type="projects.Project",
        object_id=project.reference,
        object_label=str(project),
        actor_membership=actor_membership,
        after=_snapshot(project),
        request=request,
    )
    return project


@transaction.atomic
def update_project(
    *,
    actor_membership: CompanyMembership,
    project_id,
    code: str,
    name: str,
    start_date,
    status: str,
    client_name: str = "",
    location: str = "",
    end_date=None,
    manager_name: str = "",
    notes: str = "",
    request: HttpRequest | None = None,
) -> Project:
    _require_rental_edit(actor_membership)
    project = rental_project_for_company(company=actor_membership.company, identifier=project_id, for_update=True)
    # The locked project row is the serialization point for assignment creation/revision.
    # Do not lock assignment rows here: trade/rate changes lock an assignment before the
    # project, and taking both in the inverse order would create an avoidable deadlock.
    assignments = WorkerAssignment.objects.filter(company=project.company, project=project, cancelled_at__isnull=True)
    next_status = _project_status(status)
    earliest_assignment = assignments.order_by("effective_from").first()
    if earliest_assignment and start_date and start_date > earliest_assignment.effective_from:
        raise ValidationError({"start_date": "Project start date cannot move after existing assignment history."})
    if next_status == ProjectStatus.COMPLETED:
        if not end_date:
            raise ValidationError({"end_date": "Completed projects require an end date."})
        if assignments.filter(Q(effective_to__isnull=True) | Q(effective_to__gt=end_date)).exists():
            raise ValidationError({"status": "Release or transfer all assignments through the project end date before completing the project."})
    before = _snapshot(project)
    project.code = code
    project.name = name
    project.client_name = client_name
    project.location = location
    project.start_date = start_date
    project.end_date = end_date
    project.manager_name = manager_name
    project.status = next_status
    project.notes = notes
    project.updated_by = actor_membership.user
    project.full_clean()
    try:
        project.save()
    except IntegrityError as exc:
        raise ValidationError("Project code must be unique within the company.") from exc
    after = _snapshot(project)
    if before != after:
        record_audit_event(
            company=project.company,
            area=AuditArea.RENTAL,
            action="rental.project.updated",
            object_type="projects.Project",
            object_id=project.reference,
            object_label=str(project),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return project


MAX_WORKER_IMPORT_ROWS = 5000


def _resolve_supplier(*, company, supplier_id=None, supplier_code: str = "", for_update: bool = False) -> ManpowerSupplier:
    queryset = ManpowerSupplier.objects.for_company(company)
    if for_update:
        queryset = queryset.select_for_update()
    if supplier_id:
        supplier = queryset.get(pk=supplier_id)
    elif supplier_code.strip():
        supplier = queryset.get(code=supplier_code.strip().upper())
    else:
        raise ValidationError({"supplier": "A managed manpower supplier is required."})
    if supplier.status != SupplierStatus.ACTIVE:
        raise ValidationError({"supplier": "Choose an active manpower supplier."})
    return supplier


@transaction.atomic
def create_worker(
    *,
    actor_membership: CompanyMembership,
    supplier_id,
    worker_number: str,
    full_name: str,
    national_id: str = "",
    phone: str = "",
    status: str | bool = RentalWorkerStatus.ACTIVE,
    notes: str = "",
    request: HttpRequest | None = None,
) -> RentalWorker:
    _require_rental_edit(actor_membership)
    company = actor_membership.company
    supplier = _resolve_supplier(company=company, supplier_id=supplier_id, for_update=True)
    worker_number = (worker_number or "").strip() or allocate_number(company=company, key="rental.worker", prefix="RW-", padding=5)
    worker = RentalWorker(
        company=company,
        worker_number=worker_number,
        full_name=full_name,
        national_id=national_id,
        phone=phone,
        supplier=supplier,
        status=_worker_status(status),
        notes=notes,
    )
    worker.full_clean()
    try:
        worker.save()
    except IntegrityError as exc:
        raise ValidationError("Worker number and non-empty National ID/Iqama must be unique within the company.") from exc
    record_audit_event(
        company=company,
        area=AuditArea.RENTAL,
        action="rental.worker.created",
        object_type="rental_manpower.RentalWorker",
        object_id=worker.pk,
        object_label=str(worker),
        actor_membership=actor_membership,
        after=_snapshot(worker),
        request=request,
    )
    return worker


@transaction.atomic
def update_worker(
    *,
    actor_membership: CompanyMembership,
    worker_id,
    worker_number: str,
    full_name: str,
    national_id: str = "",
    phone: str = "",
    supplier_id=None,
    status: str | bool = RentalWorkerStatus.ACTIVE,
    notes: str = "",
    request: HttpRequest | None = None,
) -> RentalWorker:
    _require_rental_edit(actor_membership)
    worker = RentalWorker.objects.select_for_update().select_related("supplier").get(pk=worker_id, company=actor_membership.company)
    before = _snapshot(worker)
    if supplier_id and str(supplier_id) != str(worker.supplier_id):
        raise ValidationError({"supplier": "Worker supplier ownership cannot be changed through a master edit."})
    supplier = ManpowerSupplier.objects.for_company(worker.company).select_for_update().get(pk=worker.supplier_id)
    next_status = _worker_status(status)
    if next_status == RentalWorkerStatus.ACTIVE and supplier.status != SupplierStatus.ACTIVE:
        raise ValidationError({"supplier": "Active workers must belong to an active supplier."})
    if next_status == RentalWorkerStatus.INACTIVE:
        today = timezone.localdate()
        if WorkerAssignment.objects.select_for_update().filter(company=worker.company, worker=worker, cancelled_at__isnull=True).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=today)
        ).exists():
            raise ValidationError({"status": "Release the worker from current or scheduled assignments before making the worker inactive."})
    worker.worker_number = worker_number
    worker.full_name = full_name
    worker.national_id = national_id
    worker.phone = phone
    worker.supplier = supplier
    worker.status = next_status
    worker.notes = notes
    worker.full_clean()
    try:
        worker.save()
    except IntegrityError as exc:
        raise ValidationError("Worker number and non-empty National ID/Iqama must be unique within the company.") from exc
    after = _snapshot(worker)
    if before != after:
        record_audit_event(
            company=worker.company,
            area=AuditArea.RENTAL,
            action="rental.worker.updated",
            object_type="rental_manpower.RentalWorker",
            object_id=worker.pk,
            object_label=str(worker),
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return worker


def _validate_import_rows(*, actor_membership: CompanyMembership, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    company = actor_membership.company
    rows = list(rows)
    if len(rows) > MAX_WORKER_IMPORT_ROWS:
        raise ValidationError({"rows": f"A single worker import cannot exceed {MAX_WORKER_IMPORT_ROWS} rows."})
    normalized: list[dict[str, Any]] = []
    numbers_seen: set[str] = set()
    national_ids_seen: set[str] = set()
    existing_numbers = set(RentalWorker.objects.for_company(company).values_list("worker_number", flat=True))
    existing_national_ids = set(
        RentalWorker.objects.for_company(company).exclude(national_id="").values_list("national_id", flat=True)
    )
    suppliers_by_code = {
        item.code: item
        for item in ManpowerSupplier.objects.for_company(company).select_for_update().filter(status=SupplierStatus.ACTIVE)
    }
    suppliers_by_id = {
        str(item.id): item
        for item in suppliers_by_code.values()
    }

    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            raise ValidationError({"rows": f"Row {index} must be an object."})
        full_name = str(raw.get("full_name") or raw.get("name") or "").strip()
        worker_number = str(raw.get("worker_number") or raw.get("worker_code") or "").strip().upper()
        national_id = str(raw.get("national_id") or "").strip()
        phone = str(raw.get("phone") or "").strip()
        notes = str(raw.get("notes") or "").strip()
        status = _worker_status(str(raw.get("status") or "Active"))
        supplier_key = str(raw.get("supplier_id") or "").strip()
        supplier_code = str(raw.get("supplier_code") or "").strip().upper()
        supplier = suppliers_by_id.get(supplier_key) if supplier_key else suppliers_by_code.get(supplier_code)

        if not full_name:
            raise ValidationError({"rows": f"Row {index}: full_name is required."})
        if not supplier:
            raise ValidationError({"rows": f"Row {index}: supplier_id or active supplier_code is required."})
        if worker_number:
            if worker_number in numbers_seen or worker_number in existing_numbers:
                raise ValidationError({"rows": f"Row {index}: worker number {worker_number} already exists."})
            numbers_seen.add(worker_number)
        if national_id:
            if national_id in national_ids_seen or national_id in existing_national_ids:
                raise ValidationError({"rows": f"Row {index}: National ID/Iqama {national_id} already exists."})
            national_ids_seen.add(national_id)

        candidate = RentalWorker(
            company=company,
            worker_number=worker_number or "PENDING",
            full_name=full_name,
            national_id=national_id,
            phone=phone,
            supplier=supplier,
            status=status,
            notes=notes,
        )
        candidate.full_clean(exclude=("worker_number",) if not worker_number else None, validate_unique=False)
        normalized.append(
            {
                "worker_number": worker_number,
                "full_name": full_name,
                "national_id": national_id,
                "phone": phone,
                "supplier": supplier,
                "status": status,
                "notes": notes,
            }
        )
    if not normalized:
        raise ValidationError({"rows": "At least one worker row is required."})
    return normalized


@transaction.atomic
def import_workers(
    *,
    actor_membership: CompanyMembership,
    rows: Iterable[dict[str, Any]],
    dry_run: bool = False,
    request: HttpRequest | None = None,
) -> list[RentalWorker]:
    _require_rental_edit(actor_membership)
    normalized = _validate_import_rows(actor_membership=actor_membership, rows=rows)
    if dry_run:
        return []

    company = actor_membership.company
    created: list[RentalWorker] = []
    for row in normalized:
        number = row["worker_number"] or allocate_number(company=company, key="rental.worker", prefix="RW-", padding=5)
        worker = RentalWorker(
            company=company,
            worker_number=number,
            full_name=row["full_name"],
            national_id=row["national_id"],
            phone=row["phone"],
            supplier=row["supplier"],
            status=row["status"],
            notes=row["notes"],
        )
        worker.full_clean()
        try:
            worker.save()
        except IntegrityError as exc:
            raise ValidationError("Worker import conflicts with an existing worker record.") from exc
        created.append(worker)
        record_audit_event(
            company=company,
            area=AuditArea.RENTAL,
            action="rental.worker.imported",
            object_type="rental_manpower.RentalWorker",
            object_id=worker.pk,
            object_label=str(worker),
            actor_membership=actor_membership,
            after=_snapshot(worker),
            metadata={"import": True},
            request=request,
        )
    return created
