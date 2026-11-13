"""Expense evidence storage, intentionally outside MEDIA_ROOT and public static URLs."""
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PulsePrivateStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=str(getattr(settings, "PULSE_PRIVATE_STORAGE_ROOT",
                                      Path(settings.BASE_DIR) / "private_uploads")), base_url=None)

    def url(self, name):
        raise ValueError("Private Project Pulse evidence has no public URL. Use the authorized download view.")


def expense_upload_name(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"pulse/company-{instance.entry.project.company_id}/expense-{instance.entry_id}/{uuid4().hex}{extension}"


def validate_expense_evidence(upload):
    """Limit evidence to safe file formats; never trust supplied content type/extension."""
    extension = Path(upload.name).suffix.lower()
    if upload.size <= 0 or upload.size > 10 * 1024 * 1024:
        raise ValidationError("Evidence file must be between 1 byte and 10 MB.")
    signatures = {".pdf": lambda b: b.startswith(b"%PDF-"),
                  ".png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
                  ".jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
                  ".jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
                  ".webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP"}
    try:
        upload.seek(0)
        signature = upload.read(16)
        upload.seek(0)
    except (OSError, ValueError, AttributeError):
        raise ValidationError("Evidence file cannot be read.")
    if extension not in signatures or not signatures[extension](signature):
        raise ValidationError("Only valid PDF, PNG, JPEG and WebP files are supported.")
