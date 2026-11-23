from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.core import signing
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from apps.inventory.models import (
    StockApprovalRequest,
    StockItem,
    StockTransfer,
    StockTransferLine,
)
from apps.inventory.services.transfers import TransferAllocation

from ..models import ExportAudit
from .exporting import safe_text
from .workbook_security import WorkbookArchiveError, validate_workbook_archive

TRANSFER_SCHEMA = "sescco-stock-transfer-v1"
TRANSFER_SHEET = "Transfer Lines"
METADATA_SHEET = "SESCCO Metadata"
MAX_TRANSFER_ROWS = 5_000
MAX_QUANTITY = Decimal("9999999999999.999")
TRANSFER_HEADERS = (
    "Stock reference",
    "Material",
    "Supplier",
    "Supplier phone",
    "Current condition",
    "Available quantity",
    "Unit",
    "New quantity",
    "Used quantity",
    "Damaged quantity",
    "Lost quantity",
    "SESCCO row token",
)
OUTCOME_COLUMNS = (
    (8, StockTransferLine.Outcome.NEW),
    (9, StockTransferLine.Outcome.USED),
    (10, StockTransferLine.Outcome.DAMAGED),
    (11, StockTransferLine.Outcome.LOST),
)
_FILENAME_CLEANER = re.compile(r"[^a-z0-9-]+")
_ROW_SIGNING_SALT = "sescco.inventory.transfer-workbook.v1"


class TransferWorkbookError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedTransferWorkbook:
    manifest_id: uuid.UUID
    allocations: tuple[TransferAllocation, ...]
    selected_rows: int


def _row_snapshot(*, item, manifest_id, source_location):
    return {
        "manifest_id": str(manifest_id),
        "company_id": str(source_location.company_id),
        "source_location_reference": str(source_location.reference),
        "stock_reference": str(item.reference),
        "material": str(safe_text(item.material_name)),
        "supplier": str(safe_text(item.supplier_name)),
        "supplier_phone": str(safe_text(item.supplier_phone)),
        "condition": item.condition,
        "available": format(item.current_quantity, "f"),
        "unit_id": item.unit_id,
        "unit": str(safe_text(item.unit.symbol)),
    }


def transfer_workbook_response(*, source_location, user) -> HttpResponse:
    item_queryset = (
        StockItem.objects.for_company(source_location.company)
        .select_related("unit")
        .filter(
            location=source_location,
            status=StockItem.Status.ACTIVE,
            deleted_at__isnull=True,
            current_quantity__gt=0,
        )
        .order_by("material_name", "supplier_name", "condition", "pk")
    )
    if item_queryset.count() > MAX_TRANSFER_ROWS:
        raise TransferWorkbookError(
            f"A transfer worksheet supports at most {MAX_TRANSFER_ROWS} stock records."
        )
    items = list(item_queryset)
    if not items:
        raise TransferWorkbookError("This location has no active stock available to transfer.")

    manifest_id = uuid.uuid4()
    workbook = Workbook()
    instructions = workbook.active
    instructions.title = "Instructions"
    instructions.append(["SESCCO stock transfer worksheet"])
    instructions.append(
        ["Source", safe_text(f"{source_location.code} · {source_location.name}")]
    )
    instructions.append(["Exported at", timezone.localtime().strftime("%Y-%m-%d %H:%M:%S %Z")])
    instructions.append([])
    instructions.append(["How to use"])
    instructions.append(["1", "Enter quantities only in the four yellow quantity columns."])
    instructions.append(
        ["2", "Leave every quantity blank for stock that should remain at the source."]
    )
    instructions.append(["3", "Upload this same file and choose the destination in SESCCO MS."])
    instructions.append(
        ["4", "A project destination requires approval; an office destination posts immediately."]
    )
    instructions.append(
        ["5", "If source balances changed after export, download a fresh worksheet."]
    )
    instructions["A1"].font = Font(size=16, bold=True)
    instructions.column_dimensions["A"].width = 18
    instructions.column_dimensions["B"].width = 90

    sheet = workbook.create_sheet(TRANSFER_SHEET)
    sheet.append(TRANSFER_HEADERS)
    sheet.freeze_panes = "A2"
    header_fill = PatternFill("solid", fgColor="172033")
    input_fill = PatternFill("solid", fgColor="FFF2CC")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for item in items:
        snapshot = _row_snapshot(
            item=item,
            manifest_id=manifest_id,
            source_location=source_location,
        )
        sheet.append(
            [
                snapshot["stock_reference"],
                snapshot["material"],
                snapshot["supplier"],
                snapshot["supplier_phone"],
                snapshot["condition"],
                snapshot["available"],
                snapshot["unit"],
                None,
                None,
                None,
                None,
                signing.dumps(snapshot, salt=_ROW_SIGNING_SALT, compress=True),
            ]
        )
        row_number = sheet.max_row
        sheet.cell(row=row_number, column=6).number_format = "0.000"
        for column, _outcome in OUTCOME_COLUMNS:
            cell = sheet.cell(row=row_number, column=column)
            cell.fill = input_fill
            cell.number_format = "0.000"

    sheet.auto_filter.ref = f"A1:K{sheet.max_row}"
    widths = (40, 32, 28, 20, 18, 20, 12, 18, 18, 18, 18, 12)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width
    sheet.column_dimensions["L"].hidden = True
    quantity_validation = DataValidation(
        type="decimal",
        operator="between",
        formula1="0",
        formula2=str(MAX_QUANTITY),
        allow_blank=True,
    )
    quantity_validation.error = "Enter a positive quantity with no more than three decimals."
    quantity_validation.errorTitle = "Invalid transfer quantity"
    quantity_validation.showErrorMessage = True
    sheet.add_data_validation(quantity_validation)
    quantity_validation.add(f"H2:K{sheet.max_row}")

    metadata = workbook.create_sheet(METADATA_SHEET)
    metadata.append(["Key", "Value"])
    metadata.append(["Schema", TRANSFER_SCHEMA])
    metadata.append(["Manifest ID", str(manifest_id)])
    metadata.append(["Company ID", str(source_location.company_id)])
    metadata.append(["Source Location Reference", str(source_location.reference)])
    metadata.append(["Source Location Code", safe_text(source_location.code)])
    metadata.sheet_state = "hidden"

    output = BytesIO()
    workbook.save(output)
    ExportAudit.objects.create(
        company=source_location.company,
        dataset=ExportAudit.Dataset.TRANSFER_WORKSHEET,
        file_format=ExportAudit.Format.XLSX,
        filters={"manifest_id": str(manifest_id)},
        columns=list(TRANSFER_HEADERS),
        sort="material",
        scope_reference=str(source_location.reference),
        scope_label=f"{source_location.code} · {source_location.name}",
        row_count=len(items),
        created_by=user,
    )
    filename_code = _FILENAME_CLEANER.sub("-", source_location.code.lower()).strip("-")
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="stock-transfer-{filename_code}-{timezone.localdate()}.xlsx"'
    )
    response["Cache-Control"] = "private, no-store"
    return response


def _quantity(cell, *, row_number: int, label: str) -> Decimal:
    if cell.data_type == "f":
        raise TransferWorkbookError(f"Row {row_number}: formulas are not allowed in {label}.")
    value = cell.value
    if value in (None, ""):
        return Decimal("0")
    try:
        quantity = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TransferWorkbookError(f"Row {row_number}: {label} must be a number.") from exc
    if not quantity.is_finite() or quantity < 0 or quantity > MAX_QUANTITY:
        raise TransferWorkbookError(f"Row {row_number}: {label} is outside the allowed range.")
    if quantity.as_tuple().exponent < -3:
        raise TransferWorkbookError(
            f"Row {row_number}: {label} may contain at most three decimal places."
        )
    return quantity


def parse_transfer_workbook(*, source_file, company, source_location):
    payload = source_file.read()
    try:
        source_file.seek(0)
    except (AttributeError, OSError):
        pass
    try:
        validate_workbook_archive(payload)
    except WorkbookArchiveError as exc:
        raise TransferWorkbookError(str(exc)) from exc
    try:
        workbook = load_workbook(BytesIO(payload), data_only=False, read_only=True)
    except Exception as exc:
        raise TransferWorkbookError("The Excel workbook could not be read safely.") from exc

    try:
        if TRANSFER_SHEET not in workbook.sheetnames or METADATA_SHEET not in workbook.sheetnames:
            raise TransferWorkbookError(
                "This is not a SESCCO stock transfer worksheet. Download a fresh worksheet."
            )
        metadata_sheet = workbook[METADATA_SHEET]
        if metadata_sheet.max_row > 20 or metadata_sheet.max_column > 2:
            raise TransferWorkbookError("The transfer worksheet metadata is invalid.")
        metadata = {
            str(row[0].value or "").strip(): str(row[1].value or "").strip()
            for row in metadata_sheet.iter_rows(min_row=2, max_col=2)
            if row[0].value
        }
        if metadata.get("Schema") != TRANSFER_SCHEMA:
            raise TransferWorkbookError("The transfer worksheet version is not supported.")
        try:
            manifest_id = uuid.UUID(metadata.get("Manifest ID", ""))
        except (ValueError, TypeError) as exc:
            raise TransferWorkbookError("The transfer worksheet manifest ID is invalid.") from exc
        if metadata.get("Company ID") != str(company.pk):
            raise TransferWorkbookError("This transfer worksheet belongs to another company.")
        if metadata.get("Source Location Reference") != str(source_location.reference):
            raise TransferWorkbookError("This worksheet was exported from another source location.")

        already_imported = (
            StockApprovalRequest.objects.for_company(company)
            .filter(kind=StockApprovalRequest.Kind.TRANSFER, idempotency_key=manifest_id)
            .exists()
            or StockTransfer.objects.for_company(company)
            .filter(idempotency_key=manifest_id)
            .exists()
        )
        if already_imported:
            return ParsedTransferWorkbook(
                manifest_id=manifest_id,
                allocations=(),
                selected_rows=0,
            )

        sheet = workbook[TRANSFER_SHEET]
        if sheet.max_row > MAX_TRANSFER_ROWS + 1 or sheet.max_column > len(TRANSFER_HEADERS):
            raise TransferWorkbookError(
                f"Transfer worksheets may contain at most {MAX_TRANSFER_ROWS} stock rows."
            )
        headers = tuple(sheet.cell(row=1, column=index).value for index in range(1, 13))
        if headers != TRANSFER_HEADERS:
            raise TransferWorkbookError(
                "The transfer worksheet columns were changed. Download a fresh worksheet."
            )

        selected = []
        seen_references = set()
        nonempty_rows = 0
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=2, max_col=12),
            start=2,
        ):
            reference_value = str(row[0].value or "").strip()
            if not reference_value and not any(cell.value not in (None, "") for cell in row[7:11]):
                continue
            nonempty_rows += 1
            if nonempty_rows > MAX_TRANSFER_ROWS:
                raise TransferWorkbookError(
                    f"Transfer worksheets may contain at most {MAX_TRANSFER_ROWS} stock rows."
                )
            quantities = tuple(
                (
                    outcome,
                    _quantity(
                        row[column - 1],
                        row_number=row_number,
                        label=f"{outcome} quantity",
                    ),
                )
                for column, outcome in OUTCOME_COLUMNS
            )
            if not any(quantity > 0 for _outcome, quantity in quantities):
                continue
            token_cell = row[11]
            if token_cell.data_type == "f":
                raise TransferWorkbookError(
                    f"Row {row_number}: formulas are not allowed in the row token."
                )
            try:
                snapshot = signing.loads(
                    str(token_cell.value or ""),
                    salt=_ROW_SIGNING_SALT,
                )
            except signing.BadSignature as exc:
                raise TransferWorkbookError(
                    f"Row {row_number}: the stock row token is invalid. Download a fresh worksheet."
                ) from exc
            expected_context = {
                "manifest_id": str(manifest_id),
                "company_id": str(company.pk),
                "source_location_reference": str(source_location.reference),
            }
            if any(snapshot.get(key) != value for key, value in expected_context.items()):
                raise TransferWorkbookError(
                    f"Row {row_number}: the stock row belongs to another worksheet or location."
                )
            displayed_snapshot = {
                "stock_reference": reference_value,
                "material": str(row[1].value or ""),
                "supplier": str(row[2].value or ""),
                "supplier_phone": str(row[3].value or ""),
                "condition": str(row[4].value or "").strip().lower(),
                "available": str(row[5].value or "").strip(),
                "unit": str(row[6].value or ""),
            }
            if any(snapshot.get(key) != value for key, value in displayed_snapshot.items()):
                raise TransferWorkbookError(
                    f"Row {row_number}: protected stock fields were changed. "
                    "Download a fresh worksheet."
                )
            try:
                reference = uuid.UUID(snapshot["stock_reference"])
            except (KeyError, ValueError, TypeError) as exc:
                raise TransferWorkbookError(
                    f"Row {row_number}: stock reference is invalid."
                ) from exc
            if reference in seen_references:
                raise TransferWorkbookError(
                    f"Row {row_number}: this stock reference is selected more than once."
                )
            seen_references.add(reference)
            selected.append(
                {
                    "row_number": row_number,
                    "reference": reference,
                    "snapshot": snapshot,
                    "available": Decimal(snapshot["available"]),
                    "quantities": quantities,
                }
            )
        if not selected:
            raise TransferWorkbookError("Enter at least one transfer quantity in the worksheet.")

        items = StockItem.objects.for_company(company).select_related("unit", "location").filter(
            location=source_location,
            reference__in=[entry["reference"] for entry in selected],
            status=StockItem.Status.ACTIVE,
            deleted_at__isnull=True,
        )
        item_map = {item.reference: item for item in items}
        allocations = []
        for entry in selected:
            row_number = entry["row_number"]
            item = item_map.get(entry["reference"])
            if item is None:
                raise TransferWorkbookError(
                    f"Row {row_number}: source stock is no longer available at this location."
                )
            expected_snapshot = _row_snapshot(
                item=item,
                manifest_id=manifest_id,
                source_location=source_location,
            )
            submitted_identity = {
                key: value for key, value in entry["snapshot"].items() if key != "available"
            }
            current_identity = {
                key: value for key, value in expected_snapshot.items() if key != "available"
            }
            if submitted_identity != current_identity:
                raise TransferWorkbookError(
                    f"Row {row_number}: the source stock identity changed after export. "
                    "Download a fresh worksheet."
                )
            if entry["available"] != item.current_quantity:
                raise TransferWorkbookError(
                    f"Row {row_number}: the source balance changed after export. "
                    "Download a fresh worksheet."
                )
            total = sum((quantity for _outcome, quantity in entry["quantities"]), Decimal("0"))
            if total > entry["available"]:
                raise TransferWorkbookError(
                    f"Row {row_number}: allocated {total:f}; only "
                    f"{entry['available']:f} was exported."
                )
            for outcome, quantity in entry["quantities"]:
                if quantity > 0:
                    allocations.append(TransferAllocation(item, outcome, quantity))
        return ParsedTransferWorkbook(
            manifest_id=manifest_id,
            allocations=tuple(allocations),
            selected_rows=len(selected),
        )
    finally:
        workbook.close()
