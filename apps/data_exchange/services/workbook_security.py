from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile


MAX_WORKBOOK_MEMBERS = 5_000
MAX_WORKBOOK_UNCOMPRESSED_SIZE = 200 * 1024 * 1024
MAX_WORKBOOK_MEMBER_SIZE = 64 * 1024 * 1024
MAX_WORKBOOK_COMPRESSION_RATIO = 500
REQUIRED_WORKBOOK_MEMBERS = {
    "[Content_Types].xml",
    "xl/workbook.xml",
}


class WorkbookArchiveError(ValueError):
    pass


def _is_unsafe_member_name(name: str) -> bool:
    if not name or "\x00" in name:
        return True
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    path = PurePosixPath(normalized)
    if ".." in path.parts:
        return True
    first_part = path.parts[0] if path.parts else ""
    return len(first_part) >= 2 and first_part[1] == ":"


def validate_workbook_archive(payload: bytes) -> None:
    if not payload:
        raise WorkbookArchiveError("The workbook is empty.")

    try:
        with ZipFile(BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members:
                raise WorkbookArchiveError("The workbook archive is empty.")
            if len(members) > MAX_WORKBOOK_MEMBERS:
                raise WorkbookArchiveError("The workbook contains too many internal files.")

            member_names = {member.filename for member in members}
            missing = REQUIRED_WORKBOOK_MEMBERS - member_names
            if missing:
                raise WorkbookArchiveError("The uploaded file is not a valid Excel workbook.")

            total_uncompressed = 0
            for member in members:
                if member.is_dir():
                    continue
                if _is_unsafe_member_name(member.filename):
                    raise WorkbookArchiveError(
                        "The workbook contains an unsafe internal filename."
                    )
                if member.flag_bits & 0x1:
                    raise WorkbookArchiveError("Password-protected workbooks are not supported.")
                if member.file_size > MAX_WORKBOOK_MEMBER_SIZE:
                    raise WorkbookArchiveError(
                        "The workbook contains an internal file that is too large."
                    )

                total_uncompressed += member.file_size
                if total_uncompressed > MAX_WORKBOOK_UNCOMPRESSED_SIZE:
                    raise WorkbookArchiveError(
                        "The workbook expands beyond the safe processing limit."
                    )

                if member.file_size and member.compress_size == 0:
                    raise WorkbookArchiveError("The workbook contains an invalid compressed file.")
                if member.compress_size:
                    ratio = member.file_size / member.compress_size
                    if ratio > MAX_WORKBOOK_COMPRESSION_RATIO:
                        raise WorkbookArchiveError(
                            "The workbook contains an unsafe compression ratio."
                        )
    except BadZipFile as exc:
        raise WorkbookArchiveError("The uploaded file is not a valid XLSX/XLSM archive.") from exc
