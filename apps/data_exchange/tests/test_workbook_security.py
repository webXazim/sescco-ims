from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase
from openpyxl import Workbook

from ..services.workbook_security import (
    WorkbookArchiveError,
    validate_workbook_archive,
)


def _valid_workbook_payload() -> bytes:
    workbook = Workbook()
    workbook.active.append(["Material", "Quantity"])
    payload = BytesIO()
    workbook.save(payload)
    workbook.close()
    return payload.getvalue()


class WorkbookArchiveSecurityTests(SimpleTestCase):
    def test_accepts_valid_openxml_workbook(self):
        validate_workbook_archive(_valid_workbook_payload())

    def test_rejects_non_zip_payload(self):
        with self.assertRaisesMessage(WorkbookArchiveError, "not a valid XLSX/XLSM"):
            validate_workbook_archive(b"not an excel workbook")

    def test_rejects_archive_without_excel_structure(self):
        payload = BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("document.txt", "not a workbook")
        with self.assertRaisesMessage(WorkbookArchiveError, "not a valid Excel workbook"):
            validate_workbook_archive(payload.getvalue())

    def test_rejects_unsafe_internal_filename(self):
        payload = BytesIO()
        with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "types")
            archive.writestr("xl/workbook.xml", "workbook")
            archive.writestr("../outside.xml", "unsafe")
        with self.assertRaisesMessage(WorkbookArchiveError, "unsafe internal filename"):
            validate_workbook_archive(payload.getvalue())

    def test_rejects_excessive_expanded_size(self):
        with patch(
            "apps.data_exchange.services.workbook_security."
            "MAX_WORKBOOK_UNCOMPRESSED_SIZE",
            100,
        ):
            with self.assertRaisesMessage(WorkbookArchiveError, "safe processing limit"):
                validate_workbook_archive(_valid_workbook_payload())
