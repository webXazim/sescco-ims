"""Single-sheet Work Category / Works Excel importer (Upgrade 3/5).

The workbook is never persisted: only validated, normalized preview rows are
kept temporarily in a project-scoped import batch. No prices, expenses, stock
or contracts are created by this service.
"""
import hashlib
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from .models import PulseProgressUpdate, PulseTask, PulseWorkCategory, PulseWorkImportBatch
from .progress_services import status_for_percentage
from .work_services import _audit, _category_snapshot, _checked_project, _task_snapshot

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_WORKS = 2500
MAX_SHEET_ROWS = 15000
PREVIEW_LIFETIME = timedelta(hours=1)
_EXPECTED_HEADER = ("sn", "description", "unit", "quantity", "% completion")
_HEADER_ALIASES = ({"sn", "s/n", "serial no", "serial number"},
                   {"description", "work", "works"},
                   {"unit", "uom"}, {"quantity", "qty"},
                   {"% completion", "completion %", "completion", "progress %", "% progress"})


class WorkImportError(Exception):
    """Safe, user-visible file/preview problem."""


def _text(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _is_empty(cell):
    return cell.value is None or (isinstance(cell.value, str) and not cell.value.strip())


def _validate_text_cell(cell, *, line, column, errors):
    if cell.data_type == "f":
        errors.append(f"Row {line}, column {column}: formulas are not accepted; paste the actual value.")
        return False
    if cell.data_type == "e":
        errors.append(f"Row {line}, column {column}: Excel error value is not accepted.")
        return False
    if isinstance(cell.value, (datetime, date, bool)):
        errors.append(f"Row {line}, column {column}: enter text or a number, not a date/boolean.")
        return False
    return True


def _decimal(cell, *, line, field, errors, blank_allowed=True):
    if _is_empty(cell):
        return None if blank_allowed else Decimal(0)
    value = cell.value
    if isinstance(value, bool) or isinstance(value, (date, datetime)):
        errors.append(f"Row {line}: {field} must be numeric.")
        return None
    text = str(value).strip()
    if isinstance(value, str):
        if re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", text):
            text = text.replace(",", "")
        elif not re.fullmatch(r"[+-]?(?:\d+)(?:\.\d+)?", text):
            errors.append(f"Row {line}: {field} must be numeric.")
            return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        errors.append(f"Row {line}: {field} must be numeric.")
        return None
    if not number.is_finite():
        errors.append(f"Row {line}: {field} must be finite.")
        return None
    return number


def _completion(cell, line, errors):
    """Missing completion is ALWAYS 0%; Excel-formatted percentages use fractions."""
    if _is_empty(cell):
        return 0, True
    value = cell.value
    is_percent_format = "%" in (cell.number_format or "") and not isinstance(value, str)
    if isinstance(value, str) and value.strip().endswith("%"):
        value = value.strip()[:-1].strip()
    # Copy value to an isolated object to keep _decimal's strict validation.
    class Value:
        pass
    parsed_cell = Value()
    parsed_cell.value = value
    number = _decimal(parsed_cell, line=line, field="Completion", errors=errors, blank_allowed=False)
    if number is None:
        return None, False
    if is_percent_format:
        number *= 100
    if number < 0 or number > 100 or number != number.to_integral_value():
        errors.append(f"Row {line}: Completion must be a whole percentage between 0 and 100.")
        return None, False
    return int(number), False


def parse_workbook(upload):
    """Return normalized categories + lines, with explicit validation errors.

    A category row contains a name in column A only, followed by the exact
    five-column header and one or more numbered work rows. Repeat sections
    in the same sheet. The source Excel file is never modified.
    """
    from openpyxl import load_workbook

    filename = Path(getattr(upload, "name", "") or "").name
    if not filename.lower().endswith(".xlsx"):
        raise WorkImportError("Upload an .xlsx Excel workbook (not .xls, .xlsm, CSV or ZIP).")
    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise WorkImportError("The Excel workbook must be nonempty and no larger than 8 MB.")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise WorkImportError("This file is not a valid .xlsx workbook.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 2000 or sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise WorkImportError("Workbook expands beyond the import safety limit.")
            if any(info.flag_bits & 1 for info in archive.infolist()):
                raise WorkImportError("Encrypted Excel files cannot be imported.")
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False, keep_links=False)
    except WorkImportError:
        raise
    except Exception as exc:
        raise WorkImportError("The workbook cannot be read. Save a new, valid .xlsx file and retry.") from exc
    try:
        if len(workbook.worksheets) != 1:
            raise WorkImportError("Upload exactly one worksheet for one selected project.")
        sheet = workbook.worksheets[0]
        if (sheet.max_row or 0) > MAX_SHEET_ROWS:
            raise WorkImportError(f"The worksheet exceeds {MAX_SHEET_ROWS:,} rows. Remove unused rows.")
        if (sheet.max_column or 0) > 200:
            raise WorkImportError("The worksheet contains too many columns. Keep only columns A–E.")
        errors = []
        ordered = []
        categories = {}
        current = None
        has_header = False
        seen_header = False
        total_works = 0
        for line, excel_row in enumerate(sheet.iter_rows(min_row=1, max_col=max(5, sheet.max_column or 5)), start=1):
            if all(_is_empty(c) for c in excel_row):
                continue
            for c in excel_row:
                if not _is_empty(c):
                    _validate_text_cell(c, line=line, column=c.column_letter, errors=errors)
            if any(not _is_empty(c) for c in excel_row[5:]):
                errors.append(f"Row {line}: extra data after column E is not supported.")
                continue
            first = [_text(c.value) for c in excel_row[:5]]
            canonical = [x.lower().replace("_", " ") for x in first]
            if all(canonical[i] in _HEADER_ALIASES[i] for i in range(5)):
                seen_header = True
                if current is None:
                    errors.append(f"Row {line}: a Work Category heading must appear before the column header.")
                else:
                    has_header = True
                continue
            if first[0] and not any(first[1:]):
                if len(first[0]) > 120:
                    errors.append(f"Row {line}: Work Category name exceeds 120 characters.")
                    current = None
                    has_header = False
                    continue
                key = slugify(first[0], allow_unicode=True)[:120]
                if not key:
                    errors.append(f"Row {line}: Work Category must contain letters or numbers.")
                    current = None
                    has_header = False
                    continue
                if key not in categories:
                    categories[key] = {"name": first[0], "code": key, "row": line, "works": []}
                    ordered.append(categories[key])
                elif categories[key]["name"].casefold() != first[0].casefold():
                    # Slugification can discard symbols: "Civil & Steel" and
                    # "Civil Steel" must not silently become one work category.
                    errors.append(
                        f"Row {line}: Work Category '{first[0]}' conflicts with "
                        f"'{categories[key]['name']}' on row {categories[key]['row']}. "
                        "Give these categories distinct names."
                    )
                current = categories[key]
                has_header = False
                continue
            if current is None:
                errors.append(f"Row {line}: work row is missing a preceding Work Category heading.")
                continue
            if not has_header:
                errors.append(f"Row {line}: add the five-column header after the category heading.")
                continue
            serial = first[0]
            title = first[1]
            if not serial:
                errors.append(f"Row {line}: SN is required for every work.")
            if not title:
                errors.append(f"Row {line}: Description is required for every work.")
            if len(serial) > 48:
                errors.append(f"Row {line}: SN exceeds 48 characters.")
            if len(title) > 1000:
                errors.append(f"Row {line}: Description exceeds 1,000 characters.")
            if len(first[2]) > 32:
                errors.append(f"Row {line}: Unit exceeds 32 characters.")
            qty = _decimal(excel_row[3], line=line, field="Quantity", errors=errors)
            if qty is not None and (qty < 0 or qty.as_tuple().exponent < -4 or (qty > 0 and qty.adjusted() + 1 > 14)):
                errors.append(f"Row {line}: Quantity must be nonnegative, with up to 4 decimals and 14 whole digits.")
            percent, was_blank = _completion(excel_row[4], line, errors)
            if serial and title:
                current["works"].append({
                    "index": total_works, "row": line, "serial": serial, "title": title,
                    "unit": first[2], "quantity": str(qty) if qty is not None else None,
                    "progress": percent, "blank_percent": was_blank,
                    "category_code": current["code"], "category_name": current["name"],
                })
                total_works += 1
            if total_works > MAX_WORKS:
                raise WorkImportError(f"More than {MAX_WORKS:,} works detected. Split into smaller project imports.")
        if not seen_header or not ordered or total_works == 0:
            errors.append("No valid Work Category and Works sections were found.")
        for category in ordered:
            if not category["works"]:
                errors.append(f"Row {category['row']}: Work Category '{category['name']}' has no works.")
            seen = {}
            for row in category["works"]:
                if row["serial"].casefold() in seen:
                    errors.append(f"Row {row['row']}: duplicate SN '{row['serial']}' in '{category['name']}' (first used on row {seen[row['serial'].casefold()]}).")
                else:
                    seen[row["serial"].casefold()] = row["row"]
        return {
            "filename": filename[:255], "sha256": hashlib.sha256(raw).hexdigest(),
            "categories": ordered, "count": total_works, "errors": errors[:150],
        }
    finally:
        workbook.close()


def _task_values(task):
    return {"title": task.title, "unit": task.unit,
            "quantity": str(task.quantity) if task.quantity is not None else None,
            "progress": task.progress_percent, "status": task.status,
            "archived": bool(task.archived_at), "category_id": task.category_id,
            "serial": task.serial_number, "import_batch_id": task.last_import_batch_id}


def build_import_preview(project, parsed):
    """Compare only within selected project; use category+SN as stable identity."""
    errors = list(parsed["errors"])
    category_index = {c.code: c for c in PulseWorkCategory.objects.filter(project=project)}
    active_tasks = list(PulseTask.objects.filter(category__project=project).select_related("category"))
    by_sn = {}
    ambiguous_sn = set()
    for task in active_tasks:
        if not task.serial_number:
            continue
        key = (task.category.code, task.serial_number.casefold())
        if key in by_sn:
            ambiguous_sn.add(key)
        else:
            by_sn[key] = task
    legacy_by_title = {(t.category.code, t.title.casefold()): t for t in active_tasks if not t.serial_number}
    work_items = []
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    for category in parsed["categories"]:
        existing_cat = category_index.get(category["code"])
        if existing_cat and existing_cat.name.casefold() != category["name"].casefold():
            errors.append(
                f"Category '{category['name']}' conflicts with existing Work Category "
                f"'{existing_cat.name}'. Rename the heading or correct the existing category first."
            )
        if existing_cat and existing_cat.archived_at:
            errors.append(f"Category '{category['name']}' is archived. Restore it before importing.")
        for row in category["works"]:
            match_key = (category["code"], row["serial"].casefold())
            if match_key in ambiguous_sn:
                errors.append(
                    f"Row {row['row']}: more than one existing work in '{category['name']}' "
                    f"matches SN '{row['serial']}' when case is ignored. "
                    "Resolve the duplicate serial numbers before importing."
                )
            task = by_sn.get(match_key)
            if not task and (category["code"], row["title"].casefold()) in legacy_by_title:
                errors.append(f"Row {row['row']}: an existing work with this description has no SN. Assign its SN manually before reimporting to prevent a duplicate.")
            if task and task.archived_at:
                errors.append(f"Row {row['row']}: matching work SN {row['serial']} is archived. Restore it before importing.")
            current = _task_values(task) if task else None
            changes = []
            if current:
                for field in ("title", "unit", "quantity", "progress"):
                    if (current[field] if field != "quantity" else Decimal(current[field]) if current[field] is not None else None) != (row[field] if field != "quantity" else Decimal(row[field]) if row[field] is not None else None):
                        changes.append(field)
            kind = "new" if not task else "changed" if changes else "unchanged"
            counts[kind] += 1
            work_items.append({**row, "kind": kind, "existing_id": task.pk if task else None,
                               "before": current, "changes": changes})
    if len(errors) > 150:
        errors = errors[:150] + ["Additional validation errors omitted; correct the workbook and try again."]
    return {"filename": parsed["filename"], "sha256": parsed["sha256"],
            "category_count": len(parsed["categories"]),
            "category_names": [{"name": c["name"], "code": c["code"]} for c in parsed["categories"]],
            "items": work_items, "counts": counts, "errors": errors}


def create_preview_batch(*, project, actor, preview):
    if preview["errors"]:
        raise WorkImportError("Correct the displayed Excel validation errors before importing.")
    # Discard expired staging descriptions for this project. Applied batches
    # are cleared immediately; rejected previews are cleared on the next upload.
    PulseWorkImportBatch.objects.filter(
        project=project, status=PulseWorkImportBatch.Status.PREVIEW,
        preview_expires_at__lt=timezone.now(),
    ).update(preview_data={})
    return PulseWorkImportBatch.objects.create(
        project=project, uploaded_by=actor, filename=preview["filename"],
        sha256=preview["sha256"], status=PulseWorkImportBatch.Status.PREVIEW,
        category_count=preview["category_count"],
        preview_data=preview, preview_expires_at=timezone.now() + PREVIEW_LIFETIME,
    )


def _has_progress_authority(actor):
    return all(membership_has_permission(actor, p) for p in (
        AccessPermission.PULSE_PROGRESS_VIEW, AccessPermission.PULSE_PROGRESS_UPDATE,
    ))


@transaction.atomic
def apply_work_import(*, actor, project_id, batch_id, decisions, request=None):
    """Apply only explicit preview decisions, on the locked project, once.

    Changed existing rows default to KEEP. Only `all` explicitly modifies
    existing progress; a blank import percentage is still 0 on that path.
    """
    project = _checked_project(actor, project_id, AccessPermission.PULSE_CATEGORIES_MANAGE)
    # This is a separate permission, not implicitly granted by category management.
    required = (AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_TASKS_MANAGE)
    if not all(membership_has_permission(actor, perm) for perm in required):
        raise PermissionDenied("Work management permission is required to import works.")
    batch = get_object_or_404(PulseWorkImportBatch.objects.select_for_update(),
                              pk=batch_id, project=project, uploaded_by=actor)
    if batch.status != PulseWorkImportBatch.Status.PREVIEW:
        raise ValidationError("This import has already been applied or is no longer available.")
    if not batch.preview_expires_at or batch.preview_expires_at <= timezone.now():
        raise ValidationError("The import preview has expired. Upload the file again.")
    preview = batch.preview_data
    if not preview or preview.get("errors") or preview.get("sha256") != batch.sha256:
        raise ValidationError("The saved import preview is not valid. Upload the file again.")
    actions = []
    progress_change = False
    for item in preview["items"]:
        key = str(item["index"])
        if item["kind"] == "new":
            allowed, default = {"create", "skip"}, "create"
        elif item["kind"] == "changed":
            allowed, default = {"keep", "details", "all"}, "keep"
        else:
            allowed, default = {"keep"}, "keep"
        choice = decisions.get(key, default)
        if choice not in allowed:
            raise ValidationError(f"Invalid selection on Excel row {item['row']}.")
        actions.append((item, choice))
        if (choice == "create" and item["progress"] != 0) or (
            choice == "all" and item["before"] and item["before"]["progress"] != item["progress"]
        ):
            progress_change = True
    if progress_change and not _has_progress_authority(actor):
        raise PermissionDenied("Progress update permission is required to import nonzero or changed percentages.")

    # Validate stale source assumptions BEFORE any new categories or works exist.
    existing_categories = {c.code: c for c in PulseWorkCategory.objects.select_for_update().filter(project=project)}
    for item, choice in actions:
        cat = existing_categories.get(item["category_code"])
        if cat and cat.name.casefold() != item["category_name"].casefold():
            raise ValidationError(
                f"Category '{cat.name}' no longer matches the Excel heading on row "
                f"{item['row']}. Upload the workbook again."
            )
        if cat and cat.archived_at:
            raise ValidationError(f"Category '{cat.name}' was archived after the preview. Reupload the workbook.")
        matches = list(PulseTask.objects.select_for_update().filter(
            category__project=project, category__code=item["category_code"],
            serial_number__iexact=item["serial"],
        )[:2])
        if len(matches) > 1:
            raise ValidationError(
                f"Work SN '{item['serial']}' on Excel row {item['row']} is ambiguous. "
                "Resolve duplicate serial numbers and upload again."
            )
        existing = matches[0] if matches else None
        if item["existing_id"]:
            if not existing or existing.pk != item["existing_id"] or _task_values(existing) != item["before"]:
                raise ValidationError(f"Work on Excel row {item['row']} changed since preview. Upload the file again.")
        elif existing is not None:
            raise ValidationError(f"Work on Excel row {item['row']} now exists. Upload the file again.")
        if choice == "create" and PulseTask.objects.filter(
            category__project=project, category__code=item["category_code"],
            serial_number="", title__iexact=item["title"],
        ).exists():
            raise ValidationError(f"Existing unnumbered work conflicts with Excel row {item['row']}.")

    next_sort = (PulseWorkCategory.objects.filter(project=project).aggregate(Max("sort_order"))["sort_order__max"] or 0) + 1
    created_categories = {}
    for category in preview["category_names"]:
        cat = existing_categories.get(category["code"])
        if cat is None and any(choice == "create" and row["category_code"] == category["code"] for row, choice in actions):
            cat = PulseWorkCategory(project=project, name=category["name"],
                                    sort_order=next_sort, created_by=actor)
            cat.save()
            _audit(project, actor, "pulse.category.created", cat, None, _category_snapshot(cat), request)
            existing_categories[category["code"]] = cat
            created_categories[category["code"]] = cat
            next_sort += 1

    counters = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    for item, choice in actions:
        if choice in ("skip", "keep"):
            counters["skipped" if choice == "skip" else "unchanged"] += 1
            continue
        category = existing_categories[item["category_code"]]
        if choice == "create":
            task = PulseTask(
                category=category, serial_number=item["serial"], title=item["title"],
                unit=item["unit"], quantity=Decimal(item["quantity"]) if item["quantity"] is not None else None,
                status=status_for_percentage(item["progress"]),
                progress_percent=item["progress"], sort_order=item["index"],
                created_by=actor, last_import_batch=batch, import_row_number=item["row"],
            )
            task.save()
            _audit(project, actor, "pulse.task.imported", task, None, _task_snapshot(task), request)
            if task.progress_percent:
                PulseProgressUpdate.objects.create(
                    task=task, previous_percent=0, new_percent=task.progress_percent,
                    previous_status=PulseTask.Status.NOT_STARTED, new_status=task.status,
                    note=f"Initial completion imported from {batch.filename} row {item['row']}.", updated_by=actor,
                )
            counters["created"] += 1
        else:
            task = PulseTask.objects.select_for_update().get(pk=item["existing_id"], category=category)
            before = _task_snapshot(task)
            old_status, old_percent = task.status, task.progress_percent
            task.title, task.unit = item["title"], item["unit"]
            task.quantity = Decimal(item["quantity"]) if item["quantity"] is not None else None
            if choice == "all":
                task.progress_percent = item["progress"]
                task.status = status_for_percentage(item["progress"])
            task.last_import_batch = batch
            task.import_row_number = item["row"]
            task.save()
            if (old_status, old_percent) != (task.status, task.progress_percent):
                PulseProgressUpdate.objects.create(
                    task=task, previous_percent=old_percent, new_percent=task.progress_percent,
                    previous_status=old_status, new_status=task.status,
                    note=f"Confirmed Excel reimport from {batch.filename} row {item['row']}.", updated_by=actor,
                )
            _audit(project, actor, "pulse.task.import_updated", task, before, _task_snapshot(task), request)
            counters["updated"] += 1
    batch.status = PulseWorkImportBatch.Status.APPLIED
    batch.created_count = counters["created"]
    batch.updated_count = counters["updated"]
    batch.unchanged_count = counters["unchanged"] + counters["skipped"]
    batch.applied_at = timezone.now()
    batch.preview_data = {}  # Do not retain historical work descriptions in staging JSON.
    batch.save(update_fields=["status", "created_count", "updated_count", "unchanged_count", "applied_at", "preview_data"])
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action="pulse.work_import.applied",
        object_type="project_pulse.PulseWorkImportBatch", object_id=batch.pk,
        object_label=f"{project.code} · {batch.filename}", actor_membership=actor,
        before={}, after={"sha256": batch.sha256, "categories_created": len(created_categories), **counters},
        request=request,
    )
    return counters
