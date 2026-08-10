from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.core.forms import StyledForm
from apps.inventory.models import Unit
from apps.projects.models import Project

from .models import MAX_IMPORT_SIZE

ALLOWED_IMPORT_EXTENSIONS = {"xlsx", "xlsm"}


def validate_workbook(file):
    if not file:
        return file
    extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if extension not in ALLOWED_IMPORT_EXTENSIONS:
        raise ValidationError("Upload an XLSX or XLSM workbook.")
    if file.size > MAX_IMPORT_SIZE:
        raise ValidationError("Import workbooks must be 20 MB or smaller.")
    return file


class LegacyImportUploadForm(StyledForm):
    source_file = forms.FileField(
        label="Existing inventory workbook",
        help_text="Upload the current XLSX or XLSM file. The Database sheet is preferred.",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        help_text="All imported rows are assigned to this contracting project.",
    )
    default_unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        help_text="The existing workbook has no unit column, so choose one for new rows.",
    )
    update_existing_records = forms.BooleanField(
        required=False,
        initial=True,
        help_text=(
            "Update matching records with newer legacy price/date and non-empty description "
            "or supplier location. Current quantity is never changed."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(
            status=Project.Status.ACTIVE, deleted_at__isnull=True
        ).order_by("code")
        self.fields["default_unit"].queryset = Unit.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).order_by("name")

    def clean_source_file(self):
        return validate_workbook(self.cleaned_data.get("source_file"))


class OpeningStockImportUploadForm(StyledForm):
    source_file = forms.FileField(
        label="Opening-stock workbook",
        help_text="Use the downloadable template so every project and unit can be validated.",
    )

    def clean_source_file(self):
        return validate_workbook(self.cleaned_data.get("source_file"))


class ImportConfirmForm(StyledForm):
    confirm = forms.BooleanField(
        label="I reviewed this preview and want to import the eligible rows",
    )
    include_similar_rows = forms.BooleanField(
        required=False,
        label="Create rows that match project, material and supplier but use another phone",
        help_text=(
            "Only rows explicitly marked as similar-phone warnings are affected. Errors and "
            "duplicate workbook rows remain skipped."
        ),
    )
